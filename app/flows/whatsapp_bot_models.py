"""Modelos SQLAlchemy de la tabla `leads` (prospectos, WhatsApp o correo) en MySQL.

Una sola tabla `leads` para todo lo que es 1:1 por prospecto (deal
vinculado, identidad, estado de la explicación del bot, dedup de correos
del formulario web) — un prospecto llega por `chat_id` (WhatsApp,
`channel="whatsapp"`) o por `tracking_id` (formulario web,
`channel="email"`, ver `app.flows.graph_lead_store`); nunca por los dos.
`chat_id`/`tracking_id` son nullable porque ninguno aplica a todas
las filas — la PK es el `id` sintético. `messages` sí es 1:N (solo aplica a
leads de WhatsApp, vía `lead_id` -> `leads.id`) y se queda aparte. `checkpoints`/
`lead_checkpoints` reemplazan las columnas booleanas por punto de progreso
conversacional (ver `app.flows.whatsapp_bot_checkpoints`) — agregar un punto
nuevo es una fila en `checkpoints`, no una migración de schema. El esquema lo posee
Alembic (ver `migrations/`) — `create_all` solo se usa contra el SQLite en
memoria de los tests (`build_sqlite_engine`).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Conversation(Base):
    """Un prospecto — por `chat_id` (WhatsApp) o `tracking_id` (formulario web).

    `name`/`phone` en un lead de WhatsApp solo se escriben juntos,
    atómicamente, una vez el LLM ya tiene ambos confirmados (ver
    `_apply_confirmed_identity` en whatsapp_bot.py) — no hay estado "a
    medias" persistido acá; mientras la persona va confirmando uno a la
    vez, esa memoria vive en el propio historial de la conversación (que el
    LLM ya recibe como contexto), no en esta tabla. En un lead de correo,
    `name`/`phone` vienen ya sanitizados del formulario
    (`app.graph.lead_email_parser`).

    Los checkpoints de progreso conversacional (explicación enviada, link de
    autorización enviado, cobertura de zona) ya no son columnas acá — viven
    en `checkpoints`/`lead_checkpoints`. `status`/`detail` son el
    resultado de procesar un correo (`created`/`skipped`/`error` + motivo,
    ver `app.flows.graph_lead_store`) — `None` para un lead de WhatsApp.
    """

    __tablename__ = "leads"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    chat_id: str | None = Column(String(64), nullable=True, unique=True)
    tracking_id: str | None = Column(String(64), nullable=True, unique=True)
    channel: str = Column(String(16), nullable=False)

    deal_id: str | None = Column(String(32), nullable=True, unique=True)

    name: str | None = Column(String(255), nullable=True)
    phone: str | None = Column(String(32), nullable=True)

    # Activación explícita del bot por chat (opt-in) — arranca en False para
    # todo lead nuevo; un admin lo prende a mano desde el panel admin, o el
    # chat se auto-activa solo si es genuinamente nuevo en Waha (ver
    # `whatsapp_bot_new_chat_check.py`). Sin significado para un lead de
    # correo.
    bot_enabled: bool = Column(Boolean, nullable=False, default=False)

    # Motivo del último cambio de `bot_enabled` — se sobreescribe en cada cambio, no es
    # auditoría histórica. Valores usados hoy: `auto_new_chat`/`auto_pending_review` (chat
    # nuevo, ver whatsapp_bot_new_chat_check.py), `admin_manual` (panel admin),
    # `handoff_requested` (cliente pidió asesor), `authorization_signed` (firmó la
    # Autorización de Corretaje), `zone_out_of_coverage` (fuera de Medellín/Oriente
    # antioqueño). `None` para un lead nunca tocado o de correo.
    bot_enabled_reason: str | None = Column(String(32), nullable=True, default=None)

    # True una vez que ya se intentó importar el historial previo de WhatsApp
    # desde Waha para este chat (`app.flows.whatsapp_bot_history_seed.
    # seed_history_from_waha`), sea que haya encontrado mensajes o no —
    # evita reimportar/reanalizar en cada reactivación. Deliberadamente
    # independiente de si `messages` tiene filas: mientras `bot_enabled` está
    # apagado, `_process()` en whatsapp_bot.py ya guarda cada mensaje
    # entrante localmente (para que el chat aparezca en /admin/prospects), y
    # ese historial local NO implica que ya se haya importado nada de Waha —
    # antes de este campo, esa confusión hacía que el seed nunca se
    # ejecutara. Sin significado para un lead de correo.
    history_seeded: bool = Column(Boolean, nullable=False, default=False)

    # Resultado de procesar un correo del formulario web (solo canal "email").
    status: str | None = Column(String(16), nullable=True)
    detail: str | None = Column(Text, nullable=True)

    # Seteado explícito en código al crear la fila (mismo criterio que
    # `ConversationMessage.created_at`, que tampoco usa default de la base).
    created_at = Column(DateTime, nullable=True)


class ConversationMessage(Base):
    """Un turno del historial de chat de un lead de WhatsApp — 1:N contra `leads` por `lead_id`."""

    __tablename__ = "messages"
    __table_args__ = (Index("idx_messages_lead_id", "lead_id", "id"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    lead_id: int = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    role: str = Column(String(16), nullable=False)
    content: str = Column(Text, nullable=False)
    created_at: float = Column(Float, nullable=False)


class Checkpoint(Base):
    """Catálogo de puntos de progreso conversacional del bot (ej. `zone_coverage`,
    `explanation`, `authorization_link`) — agregar uno nuevo es una fila acá, no una
    migración. `order` define la secuencia global en la que se alcanzan; `active`
    permite desactivar uno sin borrar el histórico ya guardado en `lead_checkpoints`.
    """

    __tablename__ = "checkpoints"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    key: str = Column(String(64), nullable=False, unique=True)
    description: str | None = Column(Text, nullable=True)
    order: int = Column(Integer, nullable=False, unique=True)
    active: bool = Column(Boolean, nullable=False, default=True)


class LeadCheckpoint(Base):
    """Progreso de un lead sobre un `Checkpoint` — que exista la fila ya significa que se
    alcanzó, sin importar si `value`/`reached_at` son `NULL` (ver
    `app.flows.whatsapp_bot_checkpoints`). `reached_at` queda `NULL` en filas de backfill
    histórico sin timestamp real; se llena solo cuando la fila se crea desde código nuevo.
    """

    __tablename__ = "lead_checkpoints"
    __table_args__ = (UniqueConstraint("lead_id", "checkpoint_id", name="uq_lead_checkpoints_lead_checkpoint"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    lead_id: int = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    checkpoint_id: int = Column(Integer, ForeignKey("checkpoints.id"), nullable=False)
    value: int | None = Column(Integer, nullable=True)
    reached_at = Column(DateTime, nullable=True)


class WhatsappMessage(Base):
    """Log de dedup de `message_id` de Waha — independiente de `messages`/`leads` a propósito:
    no todo mensaje entrante llega a guardarse como turno (bot apagado globalmente, número
    fuera de `WHATSAPP_BOT_ALLOWED_NUMBERS`, media no soportada, transcripción fallida), pero
    igual necesita dedup para no reenviar la misma respuesta si Waha reemite el webhook (p.ej.
    al resincronizar historial tras reconectar la sesión luego de un restart del contenedor).
    Sin TTL: una fila por mensaje procesado, para siempre, es trivial en espacio para el
    volumen de este bot."""

    __tablename__ = "whatsapp_messages"
    __table_args__ = (UniqueConstraint("message_id", name="uq_whatsapp_messages_message_id"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    message_id: str = Column(String(128), nullable=False)
    processed_at = Column(DateTime, nullable=False)
