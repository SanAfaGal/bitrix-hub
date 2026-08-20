"""Flujo: deal de Bitrix -> contacto vinculado -> WhatsApp de bienvenida + enlace de Autorización de Corretaje.

Combina app.bitrix (leer el deal y su contacto) con app.waha (limpiar el
teléfono y enviar los mensajes) — mismo patrón que
app.flows.notify_contact, pero manda dos mensajes en secuencia en vez de uno.
"""
from __future__ import annotations

import logging
from typing import Any

from app.bitrix.client import BitrixClient
from app.forms.page import FORM_PATH
from app.waha.client import WahaClient
from app.waha.phone import extract_phone_from_contact, to_chat_id

logger = logging.getLogger(__name__)

FIELD_CONTACT_ID = "CONTACT_ID"

WELCOME_MESSAGE = "¡Hola! 👋 Soy el asistente virtual de Alberto Álvarez. Gracias por tu interés, ya te comparto el siguiente paso."
_AUTHORIZATION_LINK_MESSAGE = "Para continuar, necesitamos que completes y firmes la Autorización de Corretaje aquí: {link}"


def process_welcome_and_authorization(
    deal_id: str,
    bitrix_client: BitrixClient,
    waha_client: WahaClient,
    public_base_url: str,
    session: str | None = None,
) -> dict[str, Any]:
    """Busca el contacto vinculado al deal y le envía bienvenida + enlace de Autorización de Corretaje.

    Los dos mensajes van al mismo chat/sesión, con pausa aleatoria entre
    ellos (`WahaClient.send_text_sequence`) simulando comportamiento humano.
    """
    deal = bitrix_client.get_deal(deal_id)
    contact_id = deal.get(FIELD_CONTACT_ID)

    if not contact_id:
        logger.warning("Deal %s sin contacto vinculado (%s)", deal_id, FIELD_CONTACT_ID)
        return {"ok": False, "deal_id": deal_id, "error": "El deal no tiene contacto vinculado"}

    contact = bitrix_client.get_contact(contact_id)
    raw_phone = extract_phone_from_contact(contact)
    if not raw_phone:
        logger.warning("Contacto %s (deal %s) sin teléfono", contact_id, deal_id)
        return {"ok": False, "deal_id": deal_id, "contact_id": contact_id, "error": "El contacto no tiene teléfono"}

    chat_id = to_chat_id(raw_phone)
    if not chat_id:
        logger.warning("Teléfono de contacto %s no se pudo normalizar: %s", contact_id, raw_phone)
        return {
            "ok": False,
            "deal_id": deal_id,
            "contact_id": contact_id,
            "error": f"Teléfono inválido: {raw_phone}",
        }

    link = f"{public_base_url}{FORM_PATH}?deal_id={deal_id}"
    messages = [WELCOME_MESSAGE, _AUTHORIZATION_LINK_MESSAGE.format(link=link)]

    sent = waha_client.send_text_sequence(chat_id, messages, session=session)
    return {"ok": sent, "deal_id": deal_id, "contact_id": contact_id, "chat_id": chat_id}
