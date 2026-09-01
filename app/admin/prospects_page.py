"""HTML de la vista de prospectos/mensajes del bot de WhatsApp — sigue el patrón de app/admin/page.py.

Layout tipo WhatsApp Web: lista de chats a la izquierda, hilo del chat
seleccionado a la derecha, las dos en una sola pantalla (`render_prospects_html`)
— clic en un chat de la lista navega a `/admin/prospects/{chat_id}`, que
vuelve a renderizar ambos paneles con ese chat activo. Sin JS/AJAX: sigue
el resto del panel admin, que no tiene motor de templates ni framework de
frontend.
"""
from __future__ import annotations

import time
from datetime import datetime
from html import escape
from typing import Any

from app.admin.page import PROSPECTS_PATH, render_app_shell


def _format_datetime(ts: float | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %I:%M %p")


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
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def _display_phone(phone: str | None) -> str | None:
    """Formatea el teléfono guardado (código de país + número, sin `+`, igual que en Bitrix) solo para mostrarlo."""
    if not phone:
        return None
    return f"+{phone}"


def _deal_badge(deal_id: str | None) -> str:
    if deal_id:
        return f'<span class="prospect-badge prospect-badge--deal">Deal {escape(str(deal_id))}</span>'
    return '<span class="prospect-badge prospect-badge--nodeal">Sin deal</span>'


def _initials(name: str | None) -> str:
    if not name:
        return "?"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _avatar_html(name: str | None, *, block: str) -> str:
    """`block` es el nombre BEM del avatar (`prospect-row__avatar` o `prospect-header__avatar`)."""
    classes = block if name else f"{block} {block}--muted"
    return f'<span class="{classes}">{escape(_initials(name))}</span>'


def _list_pane(chats: list[dict[str, Any]], selected_chat_id: str | None) -> str:
    if not chats:
        return '<div class="prospect-list-pane"><div class="prospect-empty">Todavía no hay conversaciones registradas.</div></div>'

    rows = []
    for chat in chats:
        name = chat.get("confirmed_name")
        if name:
            name_html = f'<span class="prospect-row__name">{escape(name)}</span>'
        else:
            name_html = '<span class="prospect-row__name prospect-row__name--muted">Sin confirmar</span>'
        phone = _display_phone(chat.get("confirmed_phone")) or ""
        preview = (chat.get("last_content") or "").replace("\n", " ").strip()
        active = " prospect-row--active" if chat["chat_id"] == selected_chat_id else ""
        rows.append(
            f'<a class="prospect-row{active}" href="{PROSPECTS_PATH}/{escape(chat["chat_id"])}">'
            f'{_avatar_html(name, block="prospect-row__avatar")}'
            f'<div class="prospect-row__body">'
            f'<div class="prospect-row__top">'
            f"{name_html}"
            f'<span class="prospect-row__time">{escape(_format_relative(chat.get("last_created_at")))}</span>'
            f"</div>"
            f'<div class="prospect-row__bottom">'
            f'<span class="prospect-row__preview">{escape(preview)}</span>'
            f"{_deal_badge(chat.get('deal_id'))}"
            f"</div>"
            f'<span class="prospect-row__phone">{escape(phone)}</span>'
            f"</div>"
            f"</a>"
        )
    return f'<div class="prospect-list-pane">{"".join(rows)}</div>'


def _thread_pane(
    *, chat_id: str | None, chat_meta: dict[str, Any] | None, messages: list[dict[str, Any]] | None
) -> str:
    if chat_id is None:
        return (
            '<div class="prospect-thread-pane prospect-thread-pane--empty">'
            '<p class="prospect-empty">Selecciona un prospecto de la lista para ver la conversación.</p>'
            "</div>"
        )

    name = chat_meta.get("confirmed_name") if chat_meta else None
    phone = chat_meta.get("confirmed_phone") if chat_meta else None
    deal_id = chat_meta.get("deal_id") if chat_meta else None
    header_name = escape(name) if name else "Sin confirmar"
    display_phone = _display_phone(phone)
    header_phone = escape(display_phone) if display_phone else escape(chat_id)

    if not messages:
        bubbles_html = '<div class="prospect-empty">Sin mensajes todavía.</div>'
    else:
        bubbles = []
        for msg in messages:
            variant = "assistant" if msg.get("role") == "assistant" else "user"
            bubbles.append(
                f'<div class="prospect-bubble prospect-bubble--{variant}">'
                f'<div class="prospect-bubble__text">{escape(msg.get("content") or "")}</div>'
                f'<span class="prospect-bubble__time">{escape(_format_datetime(msg.get("created_at")))}</span>'
                f"</div>"
            )
        bubbles_html = "".join(bubbles)

    return f"""
    <div class="prospect-thread-pane">
      <div class="prospect-header">
        <a class="prospect-header__back" href="{PROSPECTS_PATH}" aria-label="Volver a la lista">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
        </a>
        {_avatar_html(name, block="prospect-header__avatar")}
        <div class="prospect-header__identity">
          <h1 class="prospect-header__name">{header_name}</h1>
          <span class="prospect-header__phone">{header_phone}</span>
        </div>
        {_deal_badge(deal_id)}
        <form class="prospect-header__delete-form" method="post" action="{PROSPECTS_PATH}/{escape(chat_id)}/delete"
          onsubmit="return confirm('¿Eliminar esta conversación? Esta acción no se puede deshacer.')">
          <button type="submit" class="prospect-header__delete-btn" aria-label="Eliminar conversación" title="Eliminar conversación">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
              <line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
            </svg>
          </button>
        </form>
      </div>
      <div class="prospect-thread">{bubbles_html}</div>
    </div>
    """


def render_prospects_html(
    *,
    username: str,
    chats: list[dict[str, Any]],
    selected_chat_id: str | None = None,
    selected_meta: dict[str, Any] | None = None,
    selected_messages: list[dict[str, Any]] | None = None,
) -> str:
    layout_class = "prospects-layout prospects-layout--has-selection" if selected_chat_id else "prospects-layout"
    body = f"""
    <div class="{layout_class}">
      {_list_pane(chats, selected_chat_id)}
      {_thread_pane(chat_id=selected_chat_id, chat_meta=selected_meta, messages=selected_messages)}
    </div>
    """
    return render_app_shell(username=username, active_view="prospects", title="Prospectos", sidebar="", body=body)
