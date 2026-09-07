"""Deduplicación de correos de Graph ya procesados por `app.flows.graph_lead_intake`.

Comparte la tabla `leads` (`app.flows.whatsapp_bot_models.Conversation`) con
el bot de WhatsApp — un lead de correo es una fila más, con
`channel="email"` y `email_tracking_id` en vez de `chat_id`. Reusa el mismo
pool MySQL que el bot (`whatsapp_bot_db.SessionLocal`), sin abrir uno nuevo.

A diferencia de `app.message_templates.store`, acá un fallo de MySQL NO cae
a un default silencioso: si no se puede confirmar si un correo ya fue
procesado, se lanza la excepción original en vez de asumir `False` —
procesar un correo sin poder confirmar el estado de dedup arriesga crear un
contacto/negociación duplicado en Bitrix, que es peor que simplemente
saltar ese correo en la corrida actual y reintentarlo en la siguiente.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.flows.whatsapp_bot_db import SessionLocal
from app.flows.whatsapp_bot_models import Conversation

logger = logging.getLogger(__name__)


def is_processed(email_tracking_id: str, *, session: Session | None = None) -> bool:
    """Indica si `email_tracking_id` ya tiene una fila en `leads`.

    Lanza la excepción original si la consulta a MySQL falla — ver
    docstring del módulo.
    """
    return get_processed(email_tracking_id, session=session) is not None


def get_processed(email_tracking_id: str, *, session: Session | None = None) -> dict[str, Any] | None:
    """Trae la fila guardada para `email_tracking_id` (status/deal_id/detail/created_at), o None si no existe.

    Usado por `app/graph/router.py` para que la respuesta de
    `POST /graph/process-leads` diga qué resultado quedó guardado de una
    corrida anterior, no solo que "ya se procesó". Lanza la excepción
    original si la consulta a MySQL falla — ver docstring del módulo.
    """
    own_session = session is None
    session = session or SessionLocal()
    try:
        row = session.execute(
            select(Conversation).where(Conversation.email_tracking_id == email_tracking_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "status": row.status,
            "deal_id": row.deal_id,
            "detail": row.detail,
            "processed_at": row.created_at.isoformat() if row.created_at else None,
        }
    finally:
        if own_session:
            session.close()


def mark_processed(
    email_tracking_id: str,
    *,
    status: str,
    deal_id: str | None = None,
    detail: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    session: Session | None = None,
) -> None:
    """Registra `email_tracking_id` como procesado (crea o actualiza la fila)."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        row = session.execute(
            select(Conversation).where(Conversation.email_tracking_id == email_tracking_id)
        ).scalar_one_or_none()
        if row is None:
            row = Conversation(email_tracking_id=email_tracking_id, channel="email")
            session.add(row)

        row.status = status
        row.deal_id = deal_id
        row.detail = detail
        row.name = name
        row.phone = phone
        row.created_at = datetime.now(timezone.utc)

        session.commit()
    finally:
        if own_session:
            session.close()
