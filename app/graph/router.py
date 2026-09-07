"""Endpoints HTTP de la integración con Microsoft Graph: lectura del inbox y toma de leads."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.crm.deps import get_crm_client
from app.flows import graph_lead_store as processed_store
from app.flows.graph_lead_intake import LEAD_SENDER, create_lead
from app.graph.client import GraphClient
from app.graph.deps import get_graph_client
from app.graph.lead_email_parser import parse_lead_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["Microsoft Graph"])

_SENDER_EXAMPLE = "cliente@dominio.com"


@router.get(
    "/inbox",
    summary="Listar/filtrar mensajes del inbox de la bandeja configurada (GRAPH_MAILBOX)",
)
def get_inbox(
    sender: str | None = Query(
        default=None, description="Dirección de correo del remitente a filtrar.", examples=[_SENDER_EXAMPLE]
    ),
    top: int = Query(default=25, ge=1, le=100, description="Cantidad máxima de mensajes a devolver."),
    client: GraphClient = Depends(get_graph_client),
) -> list[dict[str, Any]]:
    """Endpoint de prueba: confirma acceso al inbox y el filtrado por remitente."""
    try:
        return client.list_messages(sender=sender, top=top)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/process-leads",
    summary="Procesar correos de formulario web (Quiero Vender) -> contacto + negociación en Bitrix",
)
def post_process_leads(
    top: int = Query(default=25, ge=1, le=100, description="Cantidad máxima de correos a revisar en esta corrida."),
    client: GraphClient = Depends(get_graph_client),
) -> dict[str, Any]:
    """Lista los correos de `LEAD_SENDER`, salta los ya procesados y crea contacto+negociación para el resto.

    Disparador manual/cron por ahora (no hay suscripción push de Graph
    todavía) — ver `app/flows/graph_lead_intake.py`.

    La respuesta separa cada correo revisado en una de cuatro listas —
    `total` siempre es la suma de las cuatro:

    - **created**: procesado en ESTA corrida, era "Quiero Vender", se creó
      (o ya existía) el contacto/negociación en Bitrix. Trae `deal_id`.
    - **skipped**: procesado en ESTA corrida, pero el asunto no es "Quiero
      Vender" (ej. "Quiero Comprar"/"Quiero Arrendar") — no toca Bitrix.
      Trae `reason` (ej. `"service_type=comprar"`).
    - **errors**: procesado en ESTA corrida, era "Quiero Vender", pero algo
      falló antes de terminar (sin teléfono válido, Bitrix no devolvió
      contacto/deal, o no se pudo confirmar el estado de dedup — este
      último caso NO se marca como procesado, para reintentarlo en la
      siguiente corrida). Trae `reason` con el motivo puntual.
    - **already_processed**: NO se tocó en esta corrida — ya tenía una fila
      en `leads` (tabla compartida con el bot de WhatsApp, `channel="email"`,
      ver `app.flows.graph_lead_store`) de una corrida anterior (que puede
      haber sido cualquiera de los tres resultados de arriba). Trae el
      `status`/`deal_id`/`detail`/`processed_at` que quedó guardado
      entonces, para saber qué pasó sin tener que reprocesarlo.
    """
    try:
        crm_client = get_crm_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

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
