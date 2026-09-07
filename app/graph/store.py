"""Deduplicación de mensajes de Graph ya procesados por `app.flows.graph_lead_intake`.

A diferencia de `app.message_templates.store`, acá un fallo de MySQL NO cae
a un default silencioso: si no se puede confirmar si un mensaje ya fue
procesado, `is_processed` lanza en vez de asumir `False` — procesar un
mensaje sin poder confirmar el estado de dedup arriesga crear un
contacto/negociación duplicado en Bitrix, que es peor que simplemente
saltar ese mensaje en la corrida actual y reintentarlo en la siguiente.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.graph.db import SessionLocal
from app.graph.models import ProcessedGraphMessage

logger = logging.getLogger(__name__)


def is_processed(message_id: str, *, session: Session | None = None) -> bool:
    """Indica si `message_id` ya tiene una fila en `graph_processed_messages`.

    Lanza la excepción original si la consulta a MySQL falla — ver
    docstring del módulo.
    """
    return get_processed(message_id, session=session) is not None


def get_processed(message_id: str, *, session: Session | None = None) -> dict[str, Any] | None:
    """Trae la fila guardada para `message_id` (status/deal_id/detail/processed_at), o None si no existe.

    Usado por `app/graph/router.py` para que la respuesta de
    `POST /graph/process-leads` diga qué resultado quedó guardado de una
    corrida anterior, no solo que "ya se procesó". Lanza la excepción
    original si la consulta a MySQL falla — ver docstring del módulo.
    """
    own_session = session is None
    session = session or SessionLocal()
    try:
        row = session.get(ProcessedGraphMessage, message_id)
        if row is None:
            return None
        return {
            "status": row.status,
            "deal_id": row.deal_id,
            "detail": row.detail,
            "processed_at": row.processed_at.isoformat(),
        }
    finally:
        if own_session:
            session.close()


def mark_processed(
    message_id: str,
    *,
    status: str,
    deal_id: str | None = None,
    detail: str | None = None,
    session: Session | None = None,
) -> None:
    """Registra `message_id` como procesado (crea o actualiza la fila)."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        row = session.get(ProcessedGraphMessage, message_id)
        if row is None:
            row = ProcessedGraphMessage(message_id=message_id)
            session.add(row)

        row.processed_at = datetime.now(timezone.utc)
        row.deal_id = deal_id
        row.status = status
        row.detail = detail

        session.commit()
    finally:
        if own_session:
            session.close()
