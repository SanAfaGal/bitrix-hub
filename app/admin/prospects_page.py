"""HTML de la vista de prospectos/mensajes del bot de WhatsApp — HTML sueltos en
app/admin/templates/ + app/admin/static/ (prospects.css/prospects.js), sigue el
patrón de app/interno/. Los fragmentos repetidos (badges, filas, burbujas)
son macros Jinja en app/admin/jinja_templates/_prospects_fragments.html —
este archivo solo arma los datos (labels, iniciales) y llama a esos macros.

Layout tipo WhatsApp Web: lista de chats a la izquierda, hilo del chat
seleccionado a la derecha. La carga inicial (`render_prospects_html`) trae
las dos en una sola pantalla; cambiar de chat después es AJAX
(`prospects.js` hace fetch a `/admin/prospects/{key}/detail`, que devuelve
solo `render_thread_pane_html(...)` — no vuelve a traer/renderizar la lista
completa). El `<a href>` real de cada fila queda como fallback si JS está
desactivado o para el primer load/navegación directa.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.admin.page import PROSPECTS_PATH, render_app_shell
from app.shared.html_templates import RawHTML, render_template
from app.shared.jinja_env import get_env

_BOGOTA_TZ = ZoneInfo(os.environ.get("TZ", "America/Bogota"))
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_JINJA_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"


def _fragments():
    return get_env(str(_JINJA_TEMPLATES_DIR)).get_template("_prospects_fragments.html").module


def _format_datetime(ts: float | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, tz=_BOGOTA_TZ).strftime("%d/%m/%Y %I:%M %p")


def _format_relative(ts: float | None) -> str:
    if ts is None:
        return ""
    delta = time.time() - ts
    if delta < 60:
        return "Hace instantes"
    if delta < 3600:
        return f"Hace {int(delta // 60)} min"
    if delta < 86400:
        return f"Hace {int(delta // 3600)} h"
    return datetime.fromtimestamp(ts, tz=_BOGOTA_TZ).strftime("%d/%m/%Y")


def _display_phone(phone: str | None) -> str | None:
    """Formatea el teléfono guardado (código de país + número, sin `+`, igual que en Bitrix) solo para mostrarlo."""
    if not phone:
        return None
    return f"+{phone}"


_BOT_REASON_LABELS = {
    "auto_new_chat": "se activó solo — chat nuevo",
    "auto_pending_review": "en espera de revisión — ya tenía historial",
    "handoff_requested": "el cliente pidió un asesor",
    "authorization_signed": "autorización ya firmada",
    "zone_out_of_coverage": "fuera de zona de cobertura",
}

# "admin_manual" se guarda igual al prender y al apagar el bot a mano
# (`app.admin.router.post_activate_bot`/`post_deactivate_bot`) — el label acá
# sí distingue, según el estado actual (`bot_enabled`), para no mostrar el
# mismo "(manual)" ambiguo en los dos casos.
_BOT_REASON_LABELS_BY_ENABLED = {
    True: "activado a mano",
    False: "desactivado a mano",
}


def _bot_reason_label(bot_enabled: bool | None, reason: str | None) -> str | None:
    """`bot_enabled` es `None` para leads de correo (no aplica, ver
    `app.flows.whatsapp_bot_store.list_chats`) — no se muestra nada ahí.

    `reason` (`Conversation.bot_enabled_reason`) es el motivo del último cambio — se muestra
    entre paréntesis si hay una etiqueta conocida, para no adivinar por qué un chat quedó en
    ese estado."""
    if bot_enabled is None:
        return None
    if reason == "admin_manual":
        return _BOT_REASON_LABELS_BY_ENABLED[bot_enabled]
    return _BOT_REASON_LABELS.get(reason or "")


_BOT_TOGGLE_ICON_ON = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"'
    ' stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/>'
    '<path d="M18.36 6.64a9 9 0 1 1-12.73 0"/></svg>'
)
_BOT_TOGGLE_ICON_OFF = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"'
    ' stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>'
)


def _bot_toggle_form_html(chat_id: str, bot_enabled: bool, *, css_class: str) -> str:
    """Botón para activar/desactivar el bot del chat.

    Activar es la acción "segura" (el bot arranca en modo asistido, un
    admin siempre puede volver a apagarlo) así que se destaca en sólido;
    desactivar es la que interrumpe algo que ya está andando, por eso queda
    en rojo/outline como las demás acciones de "frenar algo" del panel (ver
    `_delete_form_html`). Ambos botones se deshabilitan al enviar — la
    llamada a `seed_history_from_waha` al activar puede tardar varios
    segundos (trae historial de Waha + análisis con LLM) y sin esto un
    doble clic dispara dos requests.
    """
    action = "deactivate" if bot_enabled else "activate"
    label = "Desactivar bot" if bot_enabled else "Activar bot"
    busy_label = "Desactivando…" if bot_enabled else "Activando…"
    icon = _BOT_TOGGLE_ICON_OFF if bot_enabled else _BOT_TOGGLE_ICON_ON
    variant = "deactivate" if bot_enabled else "activate"
    return _fragments().bot_toggle_form(PROSPECTS_PATH, chat_id, css_class, action, variant, icon, label, busy_label)


def _initials(name: str | None) -> str:
    if not name:
        return "?"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _row_key(chat: dict[str, Any]) -> str | None:
    """Clave usada en la URL de la fila — `chat_id` (WhatsApp) o `tracking_id` (correo)."""
    return chat.get("chat_id") or chat.get("tracking_id")


def _row_context(chat: dict[str, Any]) -> dict[str, Any]:
    name = chat.get("confirmed_name")
    bot_enabled = chat.get("bot_enabled")
    return {
        "key": _row_key(chat) or "",
        "name": name,
        "initials": _initials(name),
        "phone": _display_phone(chat.get("confirmed_phone")) or "",
        "channel": chat.get("channel", "whatsapp"),
        "deal_id": chat.get("deal_id"),
        "bot_enabled": bot_enabled,
        "bot_label": _bot_reason_label(bot_enabled, chat.get("bot_enabled_reason")),
        "relative_time": _format_relative(chat.get("last_created_at")),
    }


def _list_pane(chats: list[dict[str, Any]], selected_chat_id: str | None) -> str:
    rows = [_row_context(chat) for chat in chats]
    return _fragments().list_pane(rows, PROSPECTS_PATH, selected_chat_id)


def _delete_form_html(chat_id: str) -> str:
    return _fragments().delete_form(PROSPECTS_PATH, chat_id)


_EMPTY_THREAD_PANE_HTML = (
    '<div class="prospect-thread-pane prospect-thread-pane--empty">'
    '<p class="prospect-empty">Selecciona un prospecto de la lista para ver la conversación.</p>'
    "</div>"
)


def _thread_header_html(*, chat_id: str, chat_meta: dict[str, Any] | None) -> RawHTML:
    name = chat_meta.get("confirmed_name") if chat_meta else None
    phone = chat_meta.get("confirmed_phone") if chat_meta else None
    deal_id = chat_meta.get("deal_id") if chat_meta else None
    channel = chat_meta.get("channel", "whatsapp") if chat_meta else "whatsapp"
    bot_enabled = chat_meta.get("bot_enabled") if chat_meta else None
    bot_enabled_reason = chat_meta.get("bot_enabled_reason") if chat_meta else None
    display_phone = _display_phone(phone)
    header_phone = display_phone or chat_id

    actions_html = ""
    if channel == "whatsapp":
        actions_html = _bot_toggle_form_html(
            chat_id, bot_enabled, css_class="prospect-header__bot-toggle"
        ) + _delete_form_html(chat_id)

    return RawHTML(
        _fragments().thread_header(
            PROSPECTS_PATH,
            chat_id,
            name,
            _initials(name),
            header_phone,
            channel,
            deal_id,
            bot_enabled,
            _bot_reason_label(bot_enabled, bot_enabled_reason),
            actions_html,
        )
    )


def _bubbles_html(messages: list[dict[str, Any]] | None) -> RawHTML:
    items = [
        {
            "variant": "assistant" if msg.get("role") == "assistant" else "user",
            "text": msg.get("content") or "",
            "time": _format_datetime(msg.get("created_at")),
        }
        for msg in (messages or [])
    ]
    return RawHTML(_fragments().bubbles(items))


def render_thread_pane_html(
    *, chat_id: str | None, chat_meta: dict[str, Any] | None, messages: list[dict[str, Any]] | None
) -> str:
    """El panel de hilo solo (header + burbujas) — usado tanto en la página completa como
    en la respuesta del endpoint AJAX `/admin/prospects/{key}/detail` (ver prospects.js)."""
    if chat_id is None:
        return _EMPTY_THREAD_PANE_HTML
    return render_template(
        _TEMPLATES_DIR / "prospects_thread_pane.html",
        header_html=_thread_header_html(chat_id=chat_id, chat_meta=chat_meta),
        bubbles_html=_bubbles_html(messages),
    )


def render_prospects_html(
    *,
    display_name: str,
    chats: list[dict[str, Any]],
    selected_chat_id: str | None = None,
    selected_meta: dict[str, Any] | None = None,
    selected_messages: list[dict[str, Any]] | None = None,
) -> str:
    layout_class = "prospects-layout prospects-layout--has-selection" if selected_chat_id else "prospects-layout"
    body = render_template(
        _TEMPLATES_DIR / "prospects.html",
        layout_class=layout_class,
        list_pane_html=RawHTML(_list_pane(chats, selected_chat_id)),
        thread_pane_html=RawHTML(
            render_thread_pane_html(chat_id=selected_chat_id, chat_meta=selected_meta, messages=selected_messages)
        ),
    )
    return render_app_shell(
        display_name=display_name,
        active_view="prospects",
        title="Prospectos",
        sidebar="",
        body=body,
        extra_head_html=RawHTML('<link rel="stylesheet" href="/static/admin/prospects.css">'),
        extra_body_html=RawHTML('<script src="/static/admin/prospects.js" defer></script>'),
    )
