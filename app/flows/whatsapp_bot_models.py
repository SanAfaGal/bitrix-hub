"""Modelos SQLAlchemy de la tabla `leads` (prospectos, WhatsApp o correo) en MySQL.

Una sola tabla `leads` para todo lo que es 1:1 por prospecto (deal
vinculado, identidad, estado de la explicación del bot, dedup de correos
del formulario web) — un prospecto llega por `chat_id` (WhatsApp,
`channel="whatsapp"`) o por `tracking_id` (formulario web,
`channel="email"`, ver `app.flows.graph_lead_store`); nunca por los dos.
`chat_id`/`tracking_id` son nullable porque ninguno aplica a todas
las filas — la PK es el `id` sintético. `messages` sí es 1:N (solo aplica a
leads de WhatsApp, vía `lead_id` -> `leads.id`) y se queda aparte. El esquema lo posee
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

    `explanation_sent`/`authorization_link_sent` son conceptos exclusivos
    del bot de WhatsApp — quedan en su default `False` para un lead de
    correo, sin significado ahí. `status`/`detail` son el
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

    explanation_sent: bool = Column(Boolean, nullable=False, default=False)

    # Fuente de verdad LOCAL de si ya mandamos el link de Autorización de
    # Corretaje — no depende de leer el picklist `UF_CRM_1773864282733` de
    # Bitrix (`is None`/`is not None`), que puede traer un valor por defecto
    # no nulo desde que se crea el deal y hacía que el bot nunca detectara
    # "todavía no se mandó" (bug visto en producción: el bot prometía el
    # link en cada turno sin mandarlo nunca). Ver `maybe_handle_acceptance`.
    authorization_link_sent: bool = Column(Boolean, nullable=False, default=False)

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

    # Pregunta de cobertura de zona (Medellín / Oriente antioqueño) que el bot le hace al
    # cliente antes de la explicación del proceso — `zone_asked` marca que ya se mandó la
    # pregunta; `zone_in_coverage` queda en `None` hasta que la persona responda con
    # claridad (`True`/`False`). Ver `app/flows/whatsapp_bot_zone.py`. Sin significado para
    # un lead de correo.
    zone_asked: bool = Column(Boolean, nullable=False, default=False)
    zone_in_coverage: bool | None = Column(Boolean, nullable=True, default=None)

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
