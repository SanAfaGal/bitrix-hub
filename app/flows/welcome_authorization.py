"""Flujo: deal del CRM -> contacto vinculado -> enlace de Autorización de Corretaje por WhatsApp.

Combina app.crm (leer el deal y su contacto) con app.waha (formatear el
chatId y enviar el mensaje) — mismo patrón que app.flows.notify_contact.
"""
from __future__ import annotations

import logging
from typing import Any

from app.crm.protocol import CrmClient
from app.forms.link_token import sign_deal_id
from app.forms.page import FORM_PATH
from app.message_templates import store as templates_store
from app.waha.client import WahaClient
from app.waha.phone import to_chat_id

logger = logging.getLogger(__name__)


def process_welcome_and_authorization(
    deal_id: str,
    crm_client: CrmClient,
    waha_client: WahaClient,
    public_base_url: str,
    link_secret: str,
    session: str | None = None,
) -> dict[str, Any]:
    """Busca el contacto vinculado al deal y le envía el enlace de Autorización de Corretaje."""
    deal = crm_client.get_deal(deal_id)

    if crm_client.get_authorization_status(deal) == "firmada":
        logger.info("Deal %s ya tiene la Autorización de Corretaje firmada, no se reenvía el link", deal_id)
        return {"ok": True, "deal_id": deal_id, "skipped": "ya_firmada"}

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

    token = sign_deal_id(deal_id, link_secret)
    link = f"{public_base_url}{FORM_PATH}?deal_id={deal_id}&token={token}"
    text = templates_store.render_template("bitrix_authorization_link_message", link=link)

    sent = waha_client.send_text(chat_id, text, session=session)
    if sent:
        crm_client.set_authorization_status(deal_id, "pendiente_firma")
        crm_client.add_comment(deal_id, "Se envió el enlace de Autorización de Corretaje por WhatsApp.")
    return {"ok": sent, "deal_id": deal_id, "contact_id": contact_id, "chat_id": chat_id}
