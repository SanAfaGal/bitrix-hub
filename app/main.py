"""API FastAPI: punto único de webhooks de Bitrix hacia integraciones externas."""
from __future__ import annotations

import logging
import mimetypes

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Windows no siempre trae .webp registrado en su mapa de MIME types del
# sistema; sin esto, StaticFiles serviría el logo como application/octet-stream.
mimetypes.add_type("image/webp", ".webp")

from app.flows.router import router as flows_router
from app.forms.router import router as forms_router
from app.waha.router import router as waha_router
from app.xposure.router import router as xposure_router

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
        "name": "Formularios",
        "description": (
            "Formularios públicos que el cliente llena y firma desde el "
            "celular (sin apps de terceros) y que generan el PDF final."
        ),
    },
]

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
)

app.include_router(xposure_router)
app.include_router(flows_router)
app.include_router(waha_router)
app.include_router(forms_router)

# Assets de marca (favicon, logo) usados por app/forms.
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health", tags=["Salud"], summary="Estado del servicio")
def health() -> dict[str, str]:
    """Verifica que la API esté corriendo."""
    return {"status": "ok"}
