"""Modelos SQLAlchemy de las tablas de conversación del bot de WhatsApp en MySQL.

Una sola tabla `conversations` para todo lo que es 1:1 por chat (deal
vinculado, identidad, estado de la explicación) — no hay razón de negocio
para partirlo en varias tablas, todas comparten la misma PK (`chat_id`) y
las escribe el mismo proceso. `conversation_messages` sí es 1:N y se queda
aparte. El esquema lo posee Alembic (ver `migrations/`) — `create_all` solo
se usa contra el SQLite en memoria de los tests (`build_sqlite_engine`).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Conversation(Base):
    """Un prospecto por `chat_id` (JID de WhatsApp) — fuente de verdad de su identidad,
    el `deal_id` de Bitrix vinculado, y en qué punto va la explicación del proceso.

    `name`/`phone` solo se escriben juntos, atómicamente, una vez el LLM ya
    tiene ambos confirmados (ver `_apply_confirmed_identity` en
    whatsapp_bot.py) — no hay estado "a medias" persistido acá; mientras la
    persona va confirmando uno a la vez, esa memoria vive en el propio
    historial de la conversación (que el LLM ya recibe como contexto), no en
    esta tabla.
    """

    __tablename__ = "conversations"

    chat_id: str = Column(String(64), primary_key=True)
    deal_id: str | None = Column(String(32), nullable=True, unique=True)

    name: str | None = Column(String(255), nullable=True)
    phone: str | None = Column(String(32), nullable=True)

    explanation_offered: bool = Column(Boolean, nullable=False, default=False)
    explanation_sent: bool = Column(Boolean, nullable=False, default=False)

    # Fuente de verdad LOCAL de si ya mandamos el link de Autorización de
    # Corretaje — no depende de leer el picklist `UF_CRM_1773864282733` de
    # Bitrix (`is None`/`is not None`), que puede traer un valor por defecto
    # no nulo desde que se crea el deal y hacía que el bot nunca detectara
    # "todavía no se mandó" (bug visto en producción: el bot prometía el
    # link en cada turno sin mandarlo nunca). Ver `maybe_handle_acceptance`.
    authorization_link_sent: bool = Column(Boolean, nullable=False, default=False)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("idx_conversation_messages_chat_id", "chat_id", "id"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    chat_id: str = Column(
        String(64), ForeignKey("conversations.chat_id", ondelete="CASCADE"), nullable=False
    )
    role: str = Column(String(16), nullable=False)
    content: str = Column(Text, nullable=False)
    created_at: float = Column(Float, nullable=False)
