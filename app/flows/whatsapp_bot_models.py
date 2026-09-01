"""Modelos SQLAlchemy de las tablas de conversación del bot de WhatsApp en MySQL.

Reflejan el esquema ya creado en la base `bitrix_hub` (`conversations` como
tabla raíz, las demás cuelgan de ella con `chat_id` como FK `ON DELETE
CASCADE`) — no hay migraciones (alembic) en este repo, `Base.metadata.create_all`
alcanza porque las tablas ya existen en producción y esto solo cubre el caso
de una base nueva (dev/tests).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Conversation(Base):
    """Fila raíz por chat — solo existe para que las demás tablas cuelguen de una FK."""

    __tablename__ = "conversations"

    chat_id: str = Column(String(64), primary_key=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    chat_id: str = Column(
        String(64), ForeignKey("conversations.chat_id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: str = Column(String(16), nullable=False)
    content: str = Column(Text, nullable=False)
    created_at: float = Column(Float, nullable=False)


class ConversationMeta(Base):
    __tablename__ = "conversation_meta"

    chat_id: str = Column(String(64), ForeignKey("conversations.chat_id", ondelete="CASCADE"), primary_key=True)
    deal_id: str = Column(String(32), nullable=False)


class ConversationFlags(Base):
    __tablename__ = "conversation_flags"

    chat_id: str = Column(String(64), ForeignKey("conversations.chat_id", ondelete="CASCADE"), primary_key=True)
    explanation_sent: bool = Column(Boolean, nullable=False, default=False)


class ConversationIdentity(Base):
    __tablename__ = "conversation_identity"

    chat_id: str = Column(String(64), ForeignKey("conversations.chat_id", ondelete="CASCADE"), primary_key=True)
    confirmed_name: str | None = Column(String(255), nullable=True)
    confirmed_phone: str | None = Column(String(32), nullable=True)
    pending_name: str | None = Column(String(255), nullable=True)
    pending_phone: str | None = Column(String(32), nullable=True)
