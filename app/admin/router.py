"""Endpoints del panel admin: edición de plantillas de WhatsApp y configuración del bot.

Login vive en `app/auth/` (cuenta corporativa) — acá solo se exige además
`ADMIN_EMAILS` vía `Depends(require_admin)`, ver `app/auth/deps.py`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.admin.coverage_page import filter_by_estado, render_coverage_html
from app.admin.models import TemplateUpdatePayload
from app.admin.page import (
    ADMIN_ROOT_PATH,
    CONFIG_PATH,
    COVERAGE_PATH,
    PROSPECTS_PATH,
    TEMPLATES_PATH,
    render_config_html,
    render_template_editor_html,
)
from app.admin.prospects_page import render_prospects_html
from app.auth.deps import require_admin
from app.crm.deps import get_crm_client
from app.flows.whatsapp_bot import conversation_store, reply_after_activation
from app.flows.whatsapp_bot_activation import activate_bot_for_chat
from app.flows.whatsapp_bot_history_seed import seed_history_from_waha
from app.llm.deps import get_llm_client
from app.location_catalog import client as location_catalog_client
from app.message_templates import store as templates_store
from app.waha.deps import get_waha_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])


def _template_keys() -> list[str]:
    keys: list[str] = []
    for section in templates_store.TEMPLATE_SECTIONS:
        keys.extend(section["keys"])  # type: ignore[arg-type]
    return keys


@router.get(ADMIN_ROOT_PATH, summary="Entrada única al panel — redirige a la primera plantilla")
def get_admin_root(username: str = Depends(require_admin)) -> RedirectResponse:
    return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)


@router.get(TEMPLATES_PATH, summary="Redirige a la primera plantilla")
def get_templates_index(username: str = Depends(require_admin)) -> RedirectResponse:
    return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)


@router.get(f"{TEMPLATES_PATH}/{{key}}", response_class=HTMLResponse, summary="Edita una plantilla de WhatsApp", response_model=None)
def get_template_editor(key: str, username: str = Depends(require_admin)) -> HTMLResponse | RedirectResponse:
    if key not in _template_keys():
        return RedirectResponse(url=f"{TEMPLATES_PATH}/{_template_keys()[0]}", status_code=303)
    content = templates_store.get_template(key)
    return HTMLResponse(render_template_editor_html(username=username, key=key, content=content))


@router.post(f"{TEMPLATES_PATH}/{{key}}", summary="Guarda el texto de una plantilla", response_model=None)
def post_template(
    key: str, content: str = Form(default=""), username: str = Depends(require_admin)
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
def post_restore_template(key: str, username: str = Depends(require_admin)) -> HTMLResponse | RedirectResponse:
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
def get_config(username: str = Depends(require_admin)) -> HTMLResponse:
    content = templates_store.get_template(templates_store.CONFIG_KEY)
    return HTMLResponse(render_config_html(username=username, content=content))


@router.post(CONFIG_PATH, summary="Guarda el comportamiento del bot", response_model=None)
def post_config(content: str = Form(default=""), username: str = Depends(require_admin)) -> HTMLResponse:
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
def post_restore_config(username: str = Depends(require_admin)) -> HTMLResponse:
    default_content = templates_store.DEFAULT_TEMPLATES[templates_store.CONFIG_KEY]
    templates_store.set_template(templates_store.CONFIG_KEY, default_content, updated_by=username)
    return HTMLResponse(
        render_config_html(username=username, content=default_content, flash="Restaurado al valor por defecto.")
    )


@router.get(PROSPECTS_PATH, response_class=HTMLResponse, summary="Lista los prospectos que el bot está atendiendo")
def get_prospects(username: str = Depends(require_admin)) -> HTMLResponse:
    chats = conversation_store.list_chats()
    return HTMLResponse(render_prospects_html(username=username, chats=chats))


@router.post(
    f"{PROSPECTS_PATH}/{{chat_id}}/delete",
    summary="Elimina la conversación de un prospecto",
)
def post_delete_prospect(chat_id: str, username: str = Depends(require_admin)) -> RedirectResponse:
    conversation_store.delete_chat(chat_id)
    return RedirectResponse(url=PROSPECTS_PATH, status_code=303)


@router.post(
    f"{PROSPECTS_PATH}/{{chat_id}}/bot/activate",
    summary="Activa el bot para un chat, importando su historial previo de WhatsApp si hace falta",
)
def post_activate_bot(chat_id: str, username: str = Depends(require_admin)) -> RedirectResponse:
    activate_bot_for_chat(
        chat_id,
        conversation_store,
        get_waha_client,
        get_llm_client,
        get_crm_client,
        seed_history_from_waha,
        reply_after_activation,
    )
    return RedirectResponse(url=f"{PROSPECTS_PATH}/{chat_id}", status_code=303)


@router.post(
    f"{PROSPECTS_PATH}/{{chat_id}}/bot/deactivate",
    summary="Desactiva el bot para un chat",
)
def post_deactivate_bot(chat_id: str, username: str = Depends(require_admin)) -> RedirectResponse:
    conversation_store.set_bot_enabled(chat_id, False, reason="admin_manual")
    return RedirectResponse(url=f"{PROSPECTS_PATH}/{chat_id}", status_code=303)


@router.get(
    f"{PROSPECTS_PATH}/{{key}}",
    response_class=HTMLResponse,
    summary="Muestra el hilo de un prospecto junto con la lista completa",
)
def get_prospect_detail(key: str, username: str = Depends(require_admin)) -> HTMLResponse:
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
def get_coverage(estado: str = "todos", username: str = Depends(require_admin)) -> HTMLResponse:
    sectores = location_catalog_client.fetch_all_sectores()
    flash, flash_error = (None, False)
    if sectores is None:
        sectores, flash, flash_error = [], "No se pudo leer el catálogo de sectores del DWH de Mobilia.", True
    sectors = filter_by_estado(sectores, estado)
    return HTMLResponse(
        render_coverage_html(username=username, sectors=sectors, estado=estado, flash=flash, flash_error=flash_error)
    )


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
    username: str = Depends(require_admin),
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

    sectores = location_catalog_client.fetch_all_sectores()
    if sectores is None:
        sectores, flash, flash_error = [], "No se pudo leer el catálogo de sectores del DWH de Mobilia.", True
    sectors = filter_by_estado(sectores, estado)
    return HTMLResponse(
        render_coverage_html(username=username, sectors=sectors, estado=estado, flash=flash, flash_error=flash_error)
    )


@router.get(
    "/admin/{full_path:path}",
    summary="Cualquier ruta de admin sin match cae acá — redirige a la entrada única",
    include_in_schema=False,
)
def get_admin_catch_all(full_path: str, username: str = Depends(require_admin)) -> RedirectResponse:
    """Registrada al final del router a propósito: FastAPI hace match en orden de
    declaración, así que toda ruta específica de arriba (templates/config/prospects/
    cobertura) se resuelve antes de llegar acá — esto solo atrapa lo que no matcheó."""
    return RedirectResponse(url=ADMIN_ROOT_PATH, status_code=303)
