"""Modelo SQLAlchemy de la tabla `graph_processed_messages`."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProcessedGraphMessage(Base):
    """Marca un mensaje de Microsoft Graph ya procesado por `app.flows.graph_lead_intake`.

    Evita crear un contacto/negociación duplicado en Bitrix si el mismo
    correo vuelve a aparecer en una corrida posterior de `/graph/process-leads`.
    """

    __tablename__ = "graph_processed_messages"

    message_id: str = Column(String(255), primary_key=True)
    processed_at: datetime = Column(DateTime, nullable=False)
    deal_id: str | None = Column(String(32), nullable=True)
    status: str = Column(String(16), nullable=False)
    detail: str | None = Column(Text, nullable=True)
