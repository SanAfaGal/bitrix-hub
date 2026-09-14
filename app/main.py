"""API FastAPI: punto único de webhooks de Bitrix hacia integraciones externas."""
from __future__ import annotations

import logging
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Windows no siempre trae .webp registrado en su mapa de MIME types del
# sistema; sin esto, StaticFiles serviría el logo como application/octet-stream.
mimetypes.add_type("image/webp", ".webp")

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.auth.settings import load_session_settings
from app.bitrix.client import BitrixClient
from app.bitrix.settings import load_bitrix_settings
from app.flows.router import router as flows_router
from app.forms.router import router as forms_router
from app.graph.client import GraphClient
from app.graph.router import router as graph_router
from app.graph.settings import load_graph_settings
from app.home.router import router as home_router
from app.interno.router import router as interno_router
from app.location_catalog.router import router as location_catalog_router
from app.message_templates import store as templates_store
from app.scheduler import start_scheduler
from app.waha.client import WahaClient
from app.waha.router import router as waha_router
from app.waha.settings import load_waha_settings
from app.xposure.client import XposureClient
from app.xposure.router import router as xposure_router
from app.xposure.settings import load_xposure_settings

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

tags_metadata = [
    {"name": "Salud", "description": "Chequeo de disponibilidad del servicio."},
    {
        "name": "Xposure",
        "description": "Consulta de inmuebles en el portal Xposure por número de matrícula (tax roll).",
    },
    {
        "name": "Bitrix Webhooks",
        "description": (
            "Endpoints que reciben eventos de Bitrix y disparan flujos — "
            "posiblemente multi-integración (ej. Bitrix + Xposure + Waha). "
            "Ver app/flows/README.md para el patrón."
        ),
    },
    {
        "name": "Waha",
        "description": (
            "Envío y recepción de WhatsApp vía Waha, incluye el bot "
            "conversacional experimental (apagado por defecto). Flujos de "
            "negocio en app/flows/ — ver app/flows/README.md."
        ),
    },
    {
        "name": "Microsoft Graph",
        "description": (
            "Lectura del inbox de la bandeja compartida (GRAPH_MAILBOX) vía "
            "Microsoft Graph, con filtro por remitente — paso previo para el "
            "futuro flujo de creación de contacto/negociación en Bitrix a "
            "partir de correos entrantes."
        ),
    },
    {
        "name": "Formularios",
        "description": (
            "Formularios públicos que el cliente llena y firma desde el "
            "celular (sin apps de terceros) y que generan el PDF final."
        ),
    },
    {
        "name": "Admin",
        "description": (
            "Panel interno (cuenta corporativa + ADMIN_EMAILS) para editar las "
            "plantillas de WhatsApp y el comportamiento del bot sin tocar código "
            "— ver app/admin/ y app/message_templates/."
        ),
    },
    {
        "name": "Autenticación",
        "description": "Login corporativo (Microsoft Entra ID), único para todo el staff — ver app/auth/.",
    },
    {
        "name": "Interno",
        "description": (
            "Páginas privadas para el staff (cuenta corporativa, sin ADMIN_EMAILS): "
            "crear un lead y, opcionalmente, iniciar de inmediato la Autorización de "
            "Corretaje — ver app/interno/."
        ),
    },
    {
        "name": "Inicio",
        "description": (
            "Página de inicio del staff en '/' — la única URL que hay que memorizar, "
            "enlaza a Interno y (si aplica) al panel Admin — ver app/home/."
        ),
    },
]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Siembra los defaults de plantillas en MySQL si hace falta.

    El esquema (tablas de plantillas y de conversación) lo crea Alembic, no
    la app: en desarrollo, `docker-compose.override.yml` corre
    `alembic upgrade head` antes de levantar uvicorn; en producción es un
    paso manual del operador (`docker compose exec api alembic upgrade
    head`, ver Dockerfile y README, sección de despliegue).
    Best-effort: si MySQL no está disponible (ej. desarrollo local sin
    docker compose), solo loguea — el bot de WhatsApp sigue funcionando con
    los defaults hardcodeados en app/message_templates/store.py (el
    historial de conversación sí necesita MySQL, sin él no persiste).
    """
    try:
        templates_store.seed_defaults()
    except Exception:
        logger.exception("No se pudo inicializar la base de plantillas de MySQL, se seguirá con los defaults")
    _warn_if_webhook_secrets_missing()
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def _warn_if_webhook_secrets_missing() -> None:
    """Sin `WHATSAPP_WEBHOOK_SECRET`/`BITRIX_WEBHOOK_SECRET`, los webhooks quedan sin
    autenticación (`app/waha/router.py`, `app/flows/router.py`) — es válido correr así en
    desarrollo local, pero un despliegue real que lo olvide queda abierto sin que nada lo
    señale más que este warning al arrancar."""
    if not (os.getenv("WHATSAPP_WEBHOOK_SECRET") or "").strip():
        logger.warning("WHATSAPP_WEBHOOK_SECRET no está configurado — el webhook de Waha acepta cualquier request")
    if not (os.getenv("BITRIX_WEBHOOK_SECRET") or "").strip():
        logger.warning("BITRIX_WEBHOOK_SECRET no está configurado — el webhook de Bitrix acepta cualquier request")


app = FastAPI(
    title="Bitrix Integration Hub",
    version="0.1.0",
    description=(
        "Recibe webhooks de Bitrix y dispara acciones en sistemas externos: "
        "consulta de inmuebles en Xposure y envío de WhatsApp vía Waha. "
        "Cada integración vive en su propio paquete bajo `app/` — ver el "
        "README del repo para el patrón de cómo agregar una integración nueva."
    ),
    openapi_tags=tags_metadata,
    lifespan=_lifespan,
)

# Firma la cookie de sesión de todo el staff (interno + admin, ver app/auth/).
# `load_session_settings()` falla duro si falta SESSION_SECRET_KEY en .env — sin
# esto, un despliegue mal configurado firmaría cookies con un secreto público y
# permitiría forjar sesión sin login. `https_only` evita que la cookie viaje por
# HTTP (ver SESSION_HTTPS_ONLY en app/auth/settings.py para el escape hatch de
# desarrollo local sin TLS). `same_site="lax"` (no "strict"): el callback de
# Microsoft (`/auth/callback`) llega como una navegación top-level cross-site
# iniciada desde login.microsoftonline.com — con "strict" el navegador no manda
# la cookie ahí, `oauth_state` nunca llega y el login falla con 400 en todos los
# intentos. "lax" sigue bloqueando la cookie en requests cross-site que no son
# navegación top-level (POST/fetch/iframe), que es lo que de verdad protege
# contra CSRF — mismo trade-off que usa flash-view para el mismo flujo.
_session_settings = load_session_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_settings.secret,
    https_only=_session_settings.https_only,
    same_site="lax",
)

app.include_router(xposure_router)
app.include_router(flows_router)
app.include_router(waha_router)
app.include_router(forms_router)
app.include_router(graph_router)
app.include_router(location_catalog_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(interno_router)
app.include_router(home_router)

# CSS/JS propios de las páginas privadas de app/interno/ y app/home/ (HTML/CSS/JS
# sueltos, ver sus README). Deben montarse ANTES de "/static": Starlette resuelve
# los Mount por prefijo en el orden en que se registran, así que si "/static"
# fuera primero se quedaría con toda request bajo "/static/interno/..." o
# "/static/home/..." (prefix match) antes de que estos mounts más específicos
# llegaran a verla.
app.mount("/static/interno", StaticFiles(directory="app/interno/static"), name="static-interno")
app.mount("/static/home", StaticFiles(directory="app/home/static"), name="static-home")
app.mount("/static/admin", StaticFiles(directory="app/admin/static"), name="static-admin")
# JS compartido entre paquetes (ver app/shared/field_validation_script.py) —
# app/interno/ lo carga como <script src>, no inline como app/forms/.
app.mount("/static/shared", StaticFiles(directory="app/shared/static"), name="static-shared")
# Assets de marca (favicon, logo) usados por app/forms y app/admin.
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health", tags=["Salud"], summary="Estado del servicio")
def health() -> dict[str, str]:
    """Verifica que la API esté corriendo.

    Deliberadamente no consulta integraciones externas — es lo que golpea
    el healthcheck de docker-compose.yml, y una caída transitoria de
    Bitrix/Xposure/Waha no debe hacer que Docker reinicie este contenedor.
    Para eso ver `/health/integrations`.
    """
    return {"status": "ok"}


def _check_bitrix() -> bool:
    webhook_url = load_bitrix_settings()
    return BitrixClient(webhook_url).is_reachable()


def _check_xposure() -> bool:
    base_url, username, password = load_xposure_settings()
    return XposureClient(base_url, username, password).is_reachable()


def _check_waha() -> bool:
    return WahaClient(load_waha_settings()).is_reachable()


def _check_graph() -> bool:
    tenant_id, client_id, client_secret, mailbox = load_graph_settings()
    return GraphClient(tenant_id, client_id, client_secret, mailbox).is_reachable()


@app.get("/health/integrations", tags=["Salud"], summary="Estado de las integraciones externas")
def health_integrations() -> dict[str, str]:
    """Chequeo real por integración (Bitrix, Xposure, Waha, Microsoft Graph/Outlook) —
    pensado para un monitor externo (UptimeRobot, healthchecks.io, cron) que alerte
    antes de que un usuario se tope con un error. Nunca lanza: falla de config o de
    red en una integración se reporta como "error", sin tumbar el resto del chequeo."""
    results: dict[str, str] = {}
    for name, check in (
        ("bitrix", _check_bitrix),
        ("xposure", _check_xposure),
        ("waha", _check_waha),
        ("graph", _check_graph),
    ):
        try:
            results[name] = "ok" if check() else "error"
        except Exception as exc:
            logger.warning("Chequeo de disponibilidad de %s falló: %s", name, exc)
            results[name] = "error"
    return results
