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
from app.flows import graph_lead_store as processed_store
from app.graph.client import GraphClient
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


def process_inbox(client: GraphClient, crm_client: CrmClient, top: int = 25) -> dict[str, Any]:
    """Lista los correos de `LEAD_SENDER`, salta los ya procesados y crea contacto+negociación para el resto.

    Lógica compartida entre `POST /graph/process-leads` (disparo manual, ver
    `app/graph/router.py`) y el job programado (`app/scheduler.py`) — vive
    acá y no en el router para que ambos callers la reusen sin pegarle a la
    API por HTTP.

    La respuesta separa cada correo revisado en una de cuatro listas —
    `total` siempre es la suma de las cuatro: `created` (se creó o ya
    existía el contacto/negociación), `skipped` (no era "Quiero Vender"),
    `errors` (falló antes de terminar) y `already_processed` (ya tenía fila
    en `leads` de una corrida anterior).
    """
    messages = client.list_messages(sender=LEAD_SENDER, top=top)

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    already_processed: list[dict[str, Any]] = []

    for message in messages:
        message_id = message.get("id")
        if not message_id:
            continue

        entry_base = {"message_id": message_id, "subject": message.get("subject")}

        subject = message.get("subject") or ""
        body_text = (message.get("body") or {}).get("content") or ""
        lead = parse_lead_email(subject, body_text)
        # Sin ID de Seguimiento parseable (correo malformado) no hay clave de
        # negocio para dedup — se usa el id de Graph como respaldo, así el
        # correo igual queda cubierto en una corrida futura.
        dedup_key = lead.tracking_id or message_id

        try:
            previous = processed_store.get_processed(dedup_key)
            if previous is not None:
                already_processed.append({**entry_base, **previous})
                continue
        except Exception:
            logger.exception("No se pudo confirmar el estado de dedup para el mensaje %s, se omite esta corrida", message_id)
            errors.append({**entry_base, "reason": "dedup_no_confirmado"})
            continue

        result = create_lead(lead, crm_client)

        entry = {**entry_base, "reason": result.reason}
        if result.status == "created":
            entry["deal_id"] = result.deal_id
            created.append(entry)
        elif result.status == "skipped":
            skipped.append(entry)
        else:
            errors.append(entry)

        try:
            processed_store.mark_processed(
                dedup_key,
                status=result.status,
                deal_id=result.deal_id,
                detail=result.reason,
                name=result.nombre,
                phone=result.telefono,
            )
        except Exception:
            logger.exception("No se pudo marcar como procesado el mensaje %s (creado igual: %s)", message_id, result.deal_id)

    return {
        "total": len(messages),
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "already_processed": already_processed,
    }


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
    deal_id = crm_client.create_property_seller_deal(contact_id, title=deal_title, source="pagina_web")
    if deal_id is None:
        logger.error("No se pudo crear el deal en Bitrix para el contacto %s", contact_id)
        return LeadIntakeResult(
            status="error", deal_id=None, reason="deal_no_creado", nombre=lead.nombre, telefono=lead.telefono
        )

    crm_client.update_property_listing(
        deal_id,
        PropertyListing(
            property_type=lead.tipo_inmueble,
            expected_sale_price=lead.valor_estimado,
        ),
    )

    comment = _build_comment(lead)
    if comment:
        crm_client.add_comment(deal_id, comment)

    return LeadIntakeResult(status="created", deal_id=deal_id, nombre=lead.nombre, telefono=lead.telefono)


def _build_comment(lead) -> str | None:
    lines = ["Lead recibido por formulario web (Quiero Vender)."]
    if lead.zona:
        # Texto libre (sin sector_code) — no se puede vincular al Smart
        # Process de Sectores, así que queda solo en el comentario.
        lines.append(f"Zona/Sector/Barrio: {lead.zona}")
    if lead.mensaje:
        lines.append(f"Mensaje: {lead.mensaje}")
    if lead.tracking_id:
        lines.append(f"ID de Seguimiento: {lead.tracking_id}")
    return "\n".join(lines)
