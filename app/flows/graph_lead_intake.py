"""Correo del formulario web ("Quiero Vender") -> contacto + negociación en Bitrix.

Combina Microsoft Graph (`app/graph/`) y el CRM (`app.crm.protocol.CrmClient`)
— vive acá, no en `app/graph/`, por la misma regla que el resto de
`app/flows/`: los paquetes de integración no se importan entre sí. El
trigger es Graph, no un webhook de Bitrix, así que el endpoint vive en
`app/graph/router.py` en vez de `app/flows/router.py` (mismo criterio que
`whatsapp_bot.py`, ver `app/flows/README.md`).

Ejemplo real del correo que dispara esto (remitente `LEAD_SENDER`, asunto
"Nuevo envío: Formulario Servicio: Quiero Vender"):

    NOTIFICACIÓN DE FORMULARIO
    Formulario Servicio: Quiero Vender

    Se ha recibido un nuevo envío desde el sitio web:

    Nombre Completo
    Diana Herrera
    Correo Electrónico
    dianahg.seo@gmail.com
    Teléfono
    +573217549875
    Zona / Sector / Barrio
    El Poblado
    Tipo de Inmueble
    apartamento
    Valor Estimado
    6500000
    Mensaje
    Hola Busco asesoría para alquilar (con o sin muebles) o vender apartamento en el Poblado.
    Acepta Política
    on
    ID de Seguimiento: 8974dd3b-d4e8-4e5f-8e29-420b8d26665c
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.crm.protocol import CrmClient, PropertyListing
from app.graph.lead_email_parser import ParsedLead, parse_lead_email

logger = logging.getLogger(__name__)

# Remitente fijo de las notificaciones del formulario web — no es el correo
# del cliente (ese va en el cuerpo), sino la cuenta que reenvía cada envío
# del sitio a gestionventas@albertoalvarez.com.
LEAD_SENDER = "comunicados@albertoalvarez.com"

LeadIntakeStatus = Literal["created", "skipped", "error"]


@dataclass(frozen=True)
class LeadIntakeResult:
    status: LeadIntakeStatus
    deal_id: str | None
    reason: str | None = None
    nombre: str | None = None
    telefono: str | None = None


def process(message: dict[str, Any], crm_client: CrmClient) -> LeadIntakeResult:
    """Procesa un mensaje de Graph (ver shape en `app.graph.client.GraphClient.list_messages`)."""
    subject = message.get("subject") or ""
    body_text = (message.get("body") or {}).get("content") or ""

    lead = parse_lead_email(subject, body_text)
    return create_lead(lead, crm_client)


def create_lead(lead: ParsedLead, crm_client: CrmClient) -> LeadIntakeResult:
    """Crea contacto + negociación en Bitrix a partir de un `ParsedLead` ya parseado.

    Separado de `process()` para que el caller (`app/graph/router.py`) pueda
    parsear una sola vez, calcular la clave de dedup (`tracking_id`)
    ANTES de decidir si crea algo, y reusar el mismo `lead` acá — sin
    parsear el cuerpo del correo dos veces.
    """
    if lead.service_type != "vender":
        logger.info("Correo con service_type=%s, se omite (fuera de alcance)", lead.service_type)
        return LeadIntakeResult(
            status="skipped", deal_id=None, reason=f"service_type={lead.service_type}", nombre=lead.nombre, telefono=lead.telefono
        )

    if lead.telefono is None:
        logger.warning(
            "Lead de formulario web sin teléfono válido (tracking_id=%s), no se puede crear", lead.tracking_id
        )
        return LeadIntakeResult(status="error", deal_id=None, reason="sin_telefono", nombre=lead.nombre, telefono=None)

    contact_id = crm_client.find_or_create_property_seller_contact(
        lead.telefono, display_name=lead.nombre, email=lead.correo
    )
    if contact_id is None:
        logger.error(
            "No se pudo crear/encontrar el contacto en Bitrix para el lead tracking_id=%s", lead.tracking_id
        )
        return LeadIntakeResult(
            status="error", deal_id=None, reason="contacto_no_creado", nombre=lead.nombre, telefono=lead.telefono
        )

    deal_title = f"Consignación Web - {lead.nombre or lead.telefono}"
    deal_id = crm_client.find_or_create_property_seller_deal(contact_id, title=deal_title)
    if deal_id is None:
        logger.error("No se pudo crear/encontrar el deal en Bitrix para el contacto %s", contact_id)
        return LeadIntakeResult(
            status="error", deal_id=None, reason="deal_no_creado", nombre=lead.nombre, telefono=lead.telefono
        )

    crm_client.update_property_listing(
        deal_id,
        PropertyListing(
            property_type=lead.tipo_inmueble,
            sector_zone_city=lead.zona,
            expected_sale_price=lead.valor_estimado,
        ),
    )

    comment = _build_comment(lead)
    if comment:
        crm_client.add_comment(deal_id, comment)

    return LeadIntakeResult(status="created", deal_id=deal_id, nombre=lead.nombre, telefono=lead.telefono)


def _build_comment(lead) -> str | None:
    lines = ["Lead recibido por formulario web (Quiero Vender)."]
    if lead.mensaje:
        lines.append(f"Mensaje: {lead.mensaje}")
    if lead.tracking_id:
        lines.append(f"ID de Seguimiento: {lead.tracking_id}")
    return "\n".join(lines)
