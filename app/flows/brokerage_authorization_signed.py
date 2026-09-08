"""Flujo: firma del formulario de Autorización de Corretaje -> constancia en el deal (CRM) + aviso al cliente (Waha).

Ejemplo del patrón de flujo encadenado descrito en app/flows/README.md:
combina app.crm (subir el PDF, comentar, actualizar el inmueble, pausar el
bot) con app.waha (avisarle al cliente que la firma llegó). El endpoint que
genera el PDF y dispara esto vive en app/forms/router.py (el trigger es el
envío del formulario público, no un webhook de Bitrix) — pero la
composición multi-integración vive acá, no en app/forms/.
"""
from __future__ import annotations

import logging
from typing import Callable

from app.crm.protocol import CrmClient, PropertyListing
from app.forms.settings import load_signed_form_drive_folder_id
from app.message_templates import store as templates_store
from app.waha.client import WahaClient
from app.waha.phone import to_chat_id

logger = logging.getLogger(__name__)


def _upload_signed_pdf(crm_client: CrmClient, deal_id: str, filename: str, pdf_bytes: bytes) -> str | None:
    try:
        folder_id = load_signed_form_drive_folder_id()
    except RuntimeError:
        logger.exception("Falta configuración para subir el PDF firmado al drive")
        return None
    return crm_client.upload_file(folder_id, filename, pdf_bytes)


def _notify_client_signed(crm_client: CrmClient, waha_client: WahaClient, deal_id: str) -> None:
    """Le avisa al cliente por WhatsApp que su Autorización de Corretaje firmada llegó.

    Best-effort, silencioso si algo falta (sin contacto, sin teléfono, o
    falla Waha) — no debe romper `process_authorization_signed`, que ya deja
    la constancia importante (comentario + estado) en el deal aunque este
    aviso no se pueda mandar.
    """
    deal = crm_client.get_deal(deal_id)
    contact_id = crm_client.get_deal_contact_id(deal)
    if not contact_id:
        logger.warning("Deal %s firmado sin contacto vinculado, no se avisa por WhatsApp", deal_id)
        return

    contact = crm_client.get_contact(contact_id)
    raw_phone = crm_client.get_contact_phone(contact)
    chat_id = to_chat_id(raw_phone) if raw_phone else None
    if not chat_id:
        logger.warning("Deal %s firmado sin teléfono válido, no se avisa por WhatsApp", deal_id)
        return

    waha_client.send_text(chat_id, templates_store.get_template("whatsapp_authorization_signed_message"))


def process_authorization_signed(
    deal_id: str,
    filename: str,
    pdf_bytes: bytes,
    listing: PropertyListing,
    crm_client: CrmClient,
    get_waha_client: Callable[[], WahaClient],
) -> None:
    """Deja constancia de la firma en el deal: sube el PDF al drive, comenta en el timeline
    (con el link al documento si la subida funcionó), actualiza los datos del inmueble,
    marca el estado 'Firmada', pausa el bot de WhatsApp y le avisa al cliente que la recibimos.

    Pausar el bot acá (no solo cuando pide hablar con un humano) es
    deliberado: una vez firmada la Autorización, el siguiente contacto con
    el cliente lo debe llevar un asesor, no el bot conversando sobre el
    inmueble (que ya no aplica, ver `app/flows/whatsapp_bot.py`).

    Best-effort: nunca debe romper la descarga del PDF si Bitrix o Waha
    fallan — el caller (`app/forms/router.py`) ya entregó el PDF antes de
    llamar acá.
    """
    try:
        file_url = _upload_signed_pdf(crm_client, deal_id, filename, pdf_bytes)
        comment = "El cliente firmó la Autorización de Corretaje."
        if file_url:
            comment += f" Documento firmado: {file_url}"
        crm_client.add_comment(deal_id, comment)
        crm_client.update_property_listing(deal_id, listing)
        crm_client.set_authorization_status(deal_id, "firmada")
        crm_client.set_bot_active(deal_id, False)
        crm_client.add_comment(deal_id, "Bot: Autorización de Corretaje firmada, bot pausado automáticamente.")
        _notify_client_signed(crm_client, get_waha_client(), deal_id)
    except Exception:
        logger.exception("Error marcando la firma de la Autorización de Corretaje en el deal %s", deal_id)
