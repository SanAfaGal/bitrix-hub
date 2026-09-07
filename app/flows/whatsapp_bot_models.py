"""Modelos SQLAlchemy de la tabla `leads` (prospectos, WhatsApp o correo) en MySQL.

Una sola tabla `leads` para todo lo que es 1:1 por prospecto (deal
vinculado, identidad, estado de la explicación del bot, dedup de correos
del formulario web) — un prospecto llega por `chat_id` (WhatsApp,
`channel="whatsapp"`) o por `email_tracking_id` (formulario web,
`channel="email"`, ver `app.flows.graph_lead_store`); nunca por los dos.
`chat_id`/`email_tracking_id` son nullable porque ninguno aplica a todas
las filas — la PK es el `id` sintético. `conversation_messages` sí es 1:N
(solo aplica a leads de WhatsApp) y se queda aparte. El esquema lo posee
Alembic (ver `migrations/`) — `create_all` solo se usa contra el SQLite en
memoria de los tests (`build_sqlite_engine`).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Conversation(Base):
    """Un prospecto — por `chat_id` (WhatsApp) o `email_tracking_id` (formulario web).

    `name`/`phone` en un lead de WhatsApp solo se escriben juntos,
    atómicamente, una vez el LLM ya tiene ambos confirmados (ver
    `_apply_confirmed_identity` en whatsapp_bot.py) — no hay estado "a
    medias" persistido acá; mientras la persona va confirmando uno a la
    vez, esa memoria vive en el propio historial de la conversación (que el
    LLM ya recibe como contexto), no en esta tabla. En un lead de correo,
    `name`/`phone` vienen ya sanitizados del formulario
    (`app.graph.lead_email_parser`).

    `explanation_offered`/`explanation_sent`/`authorization_link_sent` son
    conceptos exclusivos del bot de WhatsApp — quedan en su default `False`
    para un lead de correo, sin significado ahí. `status`/`detail` son el
    resultado de procesar un correo (`created`/`skipped`/`error` + motivo,
    ver `app.flows.graph_lead_store`) — `None` para un lead de WhatsApp.
    """

    __tablename__ = "leads"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    chat_id: str | None = Column(String(64), nullable=True, unique=True)
    email_tracking_id: str | None = Column(String(64), nullable=True, unique=True)
    channel: str = Column(String(16), nullable=False)

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

    # Resultado de procesar un correo del formulario web (solo canal "email").
    status: str | None = Column(String(16), nullable=True)
    detail: str | None = Column(Text, nullable=True)

    # Seteado explícito en código al crear la fila (mismo criterio que
    # `ConversationMessage.created_at`, que tampoco usa default de la base).
    created_at = Column(DateTime, nullable=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("idx_conversation_messages_chat_id", "chat_id", "id"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    chat_id: str = Column(
        String(64), ForeignKey("leads.chat_id", ondelete="CASCADE"), nullable=False
    )
    role: str = Column(String(16), nullable=False)
    content: str = Column(Text, nullable=False)
    created_at: float = Column(Float, nullable=False)
