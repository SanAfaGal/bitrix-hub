"""Bienvenida de primer contacto del bot de WhatsApp: texto fijo, sin pasar por el LLM.

Separado de `whatsapp_bot.py` (ya en el límite de 500 líneas del repo) para
no seguir inflándolo. Se ejecuta antes de que `process()` invoque al LLM: si
el chat no tiene historial todavía, se resuelve si Bitrix ya conoce al
cliente por su teléfono (`CrmClient.find_contact_by_phone`) y se envía la
plantilla correspondiente (`whatsapp_welcome_known`/`whatsapp_welcome_unknown`,
ver `app/message_templates/store.py`) tal cual, sin generarla con el LLM.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.crm.protocol import CrmClient
from app.message_templates import store as templates_store
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot import ConversationStore

logger = logging.getLogger(__name__)


def maybe_send_first_contact_welcome(
    chat_id: str,
    session: str,
    waha_client: WahaClient,
    crm_client: CrmClient,
    store: "ConversationStore",
) -> bool:
    """Si el chat no tiene historial ni deal todavía, manda la bienvenida fija y la registra.

    Retorna True cuando este turno ya quedó resuelto con la bienvenida (el
    caller no debe invocar al LLM), False cuando el chat ya venía en curso
    (turno normal, sigue el flujo del LLM). El teléfono se resuelve acá
    mismo (import local para evitar el ciclo `whatsapp_bot` <-> este
    módulo) — así un chat en curso no paga ese costo de más.
    """
    if store.get_history(chat_id) or store.get_deal_id(chat_id) is not None:
        return False

    from app.flows.whatsapp_bot import _resolve_phone  # noqa: PLC0415 — evita el ciclo de imports

    phone, _ = _resolve_phone(chat_id, waha_client, session)

    contact = crm_client.find_contact_by_phone(phone) if phone else None
    name = crm_client.get_contact_full_name(contact) if contact else None

    if name:
        text = templates_store.render_template("whatsapp_welcome_known", nombre=name)
    else:
        text = templates_store.render_template("whatsapp_welcome_unknown")

    sent = waha_client.send_text(chat_id, text, session=session)
    if sent:
        store.add_turn(chat_id, "assistant", text)
    else:
        logger.error("No se pudo enviar la bienvenida de primer contacto a %s", chat_id)
    return True
