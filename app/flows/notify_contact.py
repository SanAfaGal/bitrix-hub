"""Flujo: deal de Bitrix -> contacto vinculado -> teléfono -> mensaje de WhatsApp.

Combina app.bitrix (leer el deal y su contacto) con app.waha (limpiar el
teléfono y enviar el mensaje) — mismo patrón que app.flows.deal_duplicado,
pero con Waha en vez de Xposure.
"""
from __future__ import annotations

import logging
from typing import Any

from app.bitrix.client import BitrixClient
from app.waha.client import WahaClient
from app.waha.phone import extract_phone_from_contact, to_chat_id

logger = logging.getLogger(__name__)

FIELD_CONTACT_ID = "CONTACT_ID"


def process_notify_contact(
    deal_id: str,
    text: str,
    bitrix_client: BitrixClient,
    waha_client: WahaClient,
    session: str | None = None,
) -> dict[str, Any]:
    """Busca el contacto vinculado al deal, resuelve su teléfono y le envía `text` por WhatsApp."""
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

    sent = waha_client.send_text(chat_id, text, session=session)
    return {"ok": sent, "deal_id": deal_id, "contact_id": contact_id, "chat_id": chat_id}
