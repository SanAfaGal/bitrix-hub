"""Endpoints del panel admin: login, edición de plantillas de WhatsApp y configuración del bot."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.admin.auth import log_in, log_out, verify_credentials
from app.admin.deps import require_login
from app.admin.models import LoginPayload, TemplateUpdatePayload
from app.admin.page import (
    CONFIG_PATH,
    LOGIN_PATH,
    PROSPECTS_PATH,
    TEMPLATES_PATH,
    render_config_html,
    render_login_html,
    render_template_editor_html,
)
from app.admin.prospects_page import render_prospects_html
from app.flows.whatsapp_bot import conversation_store
from app.message_templates import store as templates_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])


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


@router.get(
    f"{PROSPECTS_PATH}/{{chat_id}}",
    response_class=HTMLResponse,
    summary="Muestra el hilo de un prospecto junto con la lista completa",
)
def get_prospect_detail(chat_id: str, username: str = Depends(require_login)) -> HTMLResponse:
    chats = conversation_store.list_chats()
    confirmed_name, confirmed_phone = conversation_store.get_confirmed_identity(chat_id)
    selected_meta = {
        "confirmed_name": confirmed_name,
        "confirmed_phone": confirmed_phone,
        "deal_id": conversation_store.get_deal_id(chat_id),
    }
    selected_messages = conversation_store.get_full_history(chat_id)
    return HTMLResponse(
        render_prospects_html(
            username=username,
            chats=chats,
            selected_chat_id=chat_id,
            selected_meta=selected_meta,
            selected_messages=selected_messages,
        )
    )
