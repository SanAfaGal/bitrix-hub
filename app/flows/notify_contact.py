"""Flujo: deal del CRM -> contacto vinculado -> teléfono -> mensaje de WhatsApp.

Combina app.crm (leer el deal y su contacto) con app.waha (formatear el
chatId y enviar el mensaje) — mismo patrón que app.flows.registry_duplicate_check,
pero con Waha en vez de Xposure.
"""
from __future__ import annotations

import logging
from typing import Any

from app.crm.protocol import CrmClient
from app.waha.client import WahaClient
from app.waha.phone import to_chat_id

logger = logging.getLogger(__name__)


def process_notify_contact(
    deal_id: str,
    text: str,
    crm_client: CrmClient,
    waha_client: WahaClient,
    session: str | None = None,
) -> dict[str, Any]:
    """Busca el contacto vinculado al deal, resuelve su teléfono y le envía `text` por WhatsApp."""
    deal = crm_client.get_deal(deal_id)
    contact_id = crm_client.get_deal_contact_id(deal)

    if not contact_id:
        logger.warning("Deal %s sin contacto vinculado", deal_id)
        return {"ok": False, "deal_id": deal_id, "error": "El deal no tiene contacto vinculado"}

    contact = crm_client.get_contact(contact_id)
    raw_phone = crm_client.get_contact_phone(contact)
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
