"""Endpoints del panel admin: login, edición de plantillas de WhatsApp y configuración del bot."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.admin.auth import log_in, log_out, verify_credentials
from app.admin.coverage_page import filter_by_estado, render_coverage_html
from app.admin.deps import require_login
from app.admin.models import LoginPayload, TemplateUpdatePayload
from app.admin.page import (
    CONFIG_PATH,
    COVERAGE_PATH,
    LOGIN_PATH,
    PROSPECTS_PATH,
    TEMPLATES_PATH,
    render_config_html,
    render_login_html,
    render_template_editor_html,
)
from app.admin.prospects_page import render_prospects_html
from app.crm.deps import get_crm_client
from app.flows.whatsapp_bot import conversation_store, reply_after_activation
from app.flows.whatsapp_bot_history_seed import seed_history_from_waha
from app.llm.deps import get_llm_client
from app.location_catalog import client as location_catalog_client
from app.message_templates import store as templates_store
from app.shared.rate_limit import rate_limit
from app.waha.deps import get_waha_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])

# Sin límite de intentos, un usuario/clave débiles quedan expuestos a fuerza
# bruta si el panel llega a estar accesible desde internet.
_LOGIN_RATE_LIMIT = {"max_requests": 10, "window_seconds": 60}


def _template_keys() -> list[str]:
    keys: list[str] = []
    for section in templates_store.TEMPLATE_SECTIONS:
        keys.extend(section["keys"])  # type: ignore[arg-type]
    return keys


@router.get(LOGIN_PATH, response_class=HTMLResponse, summary="Login del panel admin")
def get_login() -> HTMLResponse:
    return HTMLResponse(render_login_html())


@router.post(LOGIN_PATH, summary="Autentica al usuario del panel admin", response_model=None)
def post_login(request: Request, username: str = Form(...), password: str = Form(...)) -> HTMLResponse | RedirectResponse:
    rate_limit(request, "admin-login", **_LOGIN_RATE_LIMIT)
    try:
        payload = LoginPayload(username=username, password=password)
    except ValidationError:
        return HTMLResponse(render_login_html(error="Usuario y clave son obligatorios."))

    if not verify_credentials(payload.username, payload.password):
        return HTMLResponse(render_login_html(error="Usuario o clave incorrectos."))

    log_in(request, payload.username)
    first_key = _template_keys()[0]
    return RedirectResponse(url=f"{TEMPLATES_PATH}/{first_key}", status_code=303)


@router.post("/admin/logout", summary="Cierra la sesión del panel admin")
def post_logout(request: Request) -> RedirectResponse:
    log_out(request)
    return RedirectResponse(url=LOGIN_PATH, status_code=303)


@router.get(TEMPLATES_PATH, summary="Redirige a la primera plantilla")
def get_templates_index(username: str = Depends(require_login)) -> RedirectResponse:
    return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)


@router.get(f"{TEMPLATES_PATH}/{{key}}", response_class=HTMLResponse, summary="Edita una plantilla de WhatsApp", response_model=None)
def get_template_editor(key: str, username: str = Depends(require_login)) -> HTMLResponse | RedirectResponse:
    if key not in _template_keys():
        return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)
    content = templates_store.get_template(key)
    return HTMLResponse(render_template_editor_html(username=username, key=key, content=content))


@router.post(f"{TEMPLATES_PATH}/{{key}}", summary="Guarda el texto de una plantilla", response_model=None)
def post_template(
    key: str, content: str = Form(default=""), username: str = Depends(require_login)
) -> HTMLResponse | RedirectResponse:
    if key not in _template_keys():
        return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)

    try:
        payload = TemplateUpdatePayload(content=content)
    except ValidationError:
        return HTMLResponse(
            render_template_editor_html(
                username=username, key=key, content=content, flash="El texto no puede estar vacío.", flash_error=True
            )
        )

    try:
        templates_store.set_template(key, payload.content, updated_by=username)
    except Exception:
        logger.exception("No se pudo guardar la plantilla %s", key)
        return HTMLResponse(
            render_template_editor_html(
                username=username,
                key=key,
                content=payload.content,
                flash="No se pudo guardar — intenta de nuevo.",
                flash_error=True,
            )
        )

    return HTMLResponse(render_template_editor_html(username=username, key=key, content=payload.content, flash="Guardado."))


@router.post(f"{TEMPLATES_PATH}/{{key}}/restore", summary="Restaura una plantilla a su valor por defecto", response_model=None)
def post_restore_template(key: str, username: str = Depends(require_login)) -> HTMLResponse | RedirectResponse:
    if key not in _template_keys():
        return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)

    default_content = templates_store.DEFAULT_TEMPLATES[key]
    templates_store.set_template(key, default_content, updated_by=username)
    return HTMLResponse(
        render_template_editor_html(
            username=username, key=key, content=default_content, flash="Restaurado al valor por defecto."
        )
    )


@router.get(CONFIG_PATH, response_class=HTMLResponse, summary="Edita el comportamiento del bot (system prompt)")
def get_config(username: str = Depends(require_login)) -> HTMLResponse:
    content = templates_store.get_template(templates_store.CONFIG_KEY)
    return HTMLResponse(render_config_html(username=username, content=content))


@router.post(CONFIG_PATH, summary="Guarda el comportamiento del bot", response_model=None)
def post_config(content: str = Form(default=""), username: str = Depends(require_login)) -> HTMLResponse:
    try:
        payload = TemplateUpdatePayload(content=content)
    except ValidationError:
        return HTMLResponse(
            render_config_html(username=username, content=content, flash="El texto no puede estar vacío.", flash_error=True)
        )

    try:
        templates_store.set_template(templates_store.CONFIG_KEY, payload.content, updated_by=username)
    except Exception:
        logger.exception("No se pudo guardar la configuración del bot")
        return HTMLResponse(
            render_config_html(
                username=username, content=payload.content, flash="No se pudo guardar — intenta de nuevo.", flash_error=True
            )
        )

    return HTMLResponse(render_config_html(username=username, content=payload.content, flash="Guardado."))


@router.post(f"{CONFIG_PATH}/restore", summary="Restaura el comportamiento del bot al valor por defecto")
def post_restore_config(username: str = Depends(require_login)) -> HTMLResponse:
    default_content = templates_store.DEFAULT_TEMPLATES[templates_store.CONFIG_KEY]
    templates_store.set_template(templates_store.CONFIG_KEY, default_content, updated_by=username)
    return HTMLResponse(
        render_config_html(username=username, content=default_content, flash="Restaurado al valor por defecto.")
    )


@router.get(PROSPECTS_PATH, response_class=HTMLResponse, summary="Lista los prospectos que el bot está atendiendo")
def get_prospects(username: str = Depends(require_login)) -> HTMLResponse:
    chats = conversation_store.list_chats()
    return HTMLResponse(render_prospects_html(username=username, chats=chats))


@router.post(
    f"{PROSPECTS_PATH}/{{chat_id}}/delete",
    summary="Elimina la conversación de un prospecto",
)
def post_delete_prospect(chat_id: str, username: str = Depends(require_login)) -> RedirectResponse:
    conversation_store.delete_chat(chat_id)
    return RedirectResponse(url=PROSPECTS_PATH, status_code=303)


@router.post(
    f"{PROSPECTS_PATH}/{{chat_id}}/bot/activate",
    summary="Activa el bot para un chat, importando su historial previo de WhatsApp si hace falta",
)
def post_activate_bot(chat_id: str, username: str = Depends(require_login)) -> RedirectResponse:
    # Si ya estaba activo no reintenta el seed — evita reimportar/reanalizar
    # de más ante un doble clic en "Activar" (ver nota de revisión de la Tarea 3).
    if not conversation_store.get_bot_enabled(chat_id):
        try:
            waha_client = get_waha_client()
            llm_client = get_llm_client()
            # `chat_lock` acá evita la carrera con un mensaje real llegando al mismo tiempo por el
            # webhook (`_process()` también toma este lock) — sin esto, `seed_history_from_waha`
            # podía pisar (`clear_messages`) un mensaje recién guardado por el webhook, o al revés.
            with conversation_store.chat_lock(chat_id):
                seed_history_from_waha(conversation_store, waha_client, llm_client, chat_id)
        except Exception:  # noqa: BLE001 — una integración mal configurada no debe romper el panel admin
            logger.exception(
                "No se pudo importar el historial de Waha al activar el bot para %s — se activa igual", chat_id
            )
        conversation_store.set_bot_enabled(chat_id, True)
        try:
            # Si el cliente tenía un mensaje sin responder (llegó mientras el chat estaba
            # apagado), se contesta de una vez acá — sin esto, se queda sin respuesta hasta
            # que el cliente escriba de nuevo, aunque el admin ya haya activado el bot mirando
            # ese mismo mensaje. Try/except aparte del de arriba: que el seed haya fallado (o no)
            # no debe impedir el intento de responder, y viceversa.
            reply_after_activation(
                chat_id, get_waha_client(), get_llm_client(), get_crm_client(), store=conversation_store
            )
        except Exception:  # noqa: BLE001 — una integración mal configurada no debe romper el panel admin
            logger.exception(
                "No se pudo responder el mensaje pendiente de %s al activar el bot", chat_id
            )
    return RedirectResponse(url=f"{PROSPECTS_PATH}/{chat_id}", status_code=303)


@router.post(
    f"{PROSPECTS_PATH}/{{chat_id}}/bot/deactivate",
    summary="Desactiva el bot para un chat",
)
def post_deactivate_bot(chat_id: str, username: str = Depends(require_login)) -> RedirectResponse:
    conversation_store.set_bot_enabled(chat_id, False, reason="admin_manual")
    return RedirectResponse(url=f"{PROSPECTS_PATH}/{chat_id}", status_code=303)


@router.get(
    f"{PROSPECTS_PATH}/{{key}}",
    response_class=HTMLResponse,
    summary="Muestra el hilo de un prospecto junto con la lista completa",
)
def get_prospect_detail(key: str, username: str = Depends(require_login)) -> HTMLResponse:
    """`key` es el `chat_id` (WhatsApp) o el `tracking_id` (lead de correo) — se resuelve buscando
    en `list_chats()`, que ya trae ambos canales mezclados (ver `app.flows.whatsapp_bot_store.list_chats`).
    """
    chats = conversation_store.list_chats()
    selected = next((c for c in chats if c["chat_id"] == key or c["tracking_id"] == key), None)

    if selected is None or selected["channel"] == "email":
        selected_meta = {
            "confirmed_name": selected["confirmed_name"] if selected else None,
            "confirmed_phone": selected["confirmed_phone"] if selected else None,
            "deal_id": selected["deal_id"] if selected else None,
            "channel": "email",
        }
        selected_messages: list = []
    else:
        confirmed_name, confirmed_phone = conversation_store.get_confirmed_identity(key)
        selected_meta = {
            "confirmed_name": confirmed_name,
            "confirmed_phone": confirmed_phone,
            "deal_id": conversation_store.get_deal_id(key),
            "channel": "whatsapp",
            "bot_enabled": conversation_store.get_bot_enabled(key),
            "bot_enabled_reason": conversation_store.get_bot_enabled_reason(key),
        }
        selected_messages = conversation_store.get_full_history(key)

    return HTMLResponse(
        render_prospects_html(
            username=username,
            chats=chats,
            selected_chat_id=key,
            selected_meta=selected_meta,
            selected_messages=selected_messages,
        )
    )


@router.get(COVERAGE_PATH, response_class=HTMLResponse, summary="Lista sectores y su cobertura de ventas")
def get_coverage(estado: str = "todos", username: str = Depends(require_login)) -> HTMLResponse:
    sectors = filter_by_estado(location_catalog_client.fetch_all_sectores(), estado)
    return HTMLResponse(render_coverage_html(username=username, sectors=sectors, estado=estado))


@router.post(
    f"{COVERAGE_PATH}/batch",
    response_class=HTMLResponse,
    summary="Activa o desactiva cobertura de ventas para los sectores seleccionados",
    response_model=None,
)
def post_coverage_batch(
    accion: str = Form(...),
    estado: str = Form("todos"),
    sector_code: list[str] = Form(default=[]),
    username: str = Depends(require_login),
) -> HTMLResponse:
    flash: str
    flash_error = False

    if accion not in ("activar", "desactivar"):
        flash, flash_error = "Acción inválida.", True
    elif not sector_code:
        flash, flash_error = "No seleccionaste ningún sector.", True
    elif location_catalog_client.set_cobertura(sector_code, covered=accion == "activar"):
        verbo = "Activada" if accion == "activar" else "Desactivada"
        flash = f"{verbo} la cobertura de {len(sector_code)} sector(es)."
    else:
        flash, flash_error = "No se pudo actualizar la cobertura en el DWH — intenta de nuevo.", True

    sectors = filter_by_estado(location_catalog_client.fetch_all_sectores(), estado)
    return HTMLResponse(
        render_coverage_html(username=username, sectors=sectors, estado=estado, flash=flash, flash_error=flash_error)
    )
