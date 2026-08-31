"""Modelo SQLAlchemy de la tabla `message_templates`."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MessageTemplate(Base):
    """Un texto editable desde el panel admin, identificado por `key` (disparador fijo en código).

    El system prompt del bot LLM es solo otra fila más (`key="whatsapp_system_prompt"`)
    — no hay una tabla aparte para eso.
    """

    __tablename__ = "message_templates"

    key: str = Column(String(64), primary_key=True)
    content: str = Column(Text, nullable=False)
    updated_at: datetime = Column(DateTime, nullable=False)
    updated_by: str | None = Column(String(64), nullable=True)
