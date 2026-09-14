"""Endpoints HTTP de la integración con Microsoft Graph: lectura del inbox y toma de leads."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_admin
from app.crm.deps import get_crm_client
from app.flows.graph_lead_intake import process_inbox
from app.graph.client import GraphClient
from app.graph.deps import get_graph_client

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
    _: str = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Endpoint de prueba: confirma acceso al inbox y el filtrado por remitente.

    Protegido con el login del panel admin: expone contenido de correo real
    de la bandeja compartida, no debe quedar accesible sin autenticación.
    """
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
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    """Lista los correos de `LEAD_SENDER`, salta los ya procesados y crea contacto+negociación para el resto.

    Protegido con el login del panel admin: dispara escritura real en
    Bitrix (contactos/negociaciones), no debe quedar accesible sin
    autenticación.

    También corre sola cada `GRAPH_LEAD_POLL_MINUTES` minutos vía el job
    programado (ver `app/scheduler.py`) — este endpoint queda para disparar
    una corrida fuera de ese ciclo o para depurar.

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

    try:
        return process_inbox(client, crm_client, top=top)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
