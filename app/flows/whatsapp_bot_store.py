"""Persistencia en MySQL (SQLAlchemy) del historial de conversación del bot de WhatsApp.

Solo el historial de turnos y el cache de `deal_id` por chat viven acá —
sobreviven a un restart/deploy del proceso, a diferencia del dedup de
mensajes (`ConversationStore._seen_message_ids` en `whatsapp_bot.py`), que
sigue en memoria porque es solo un TTL corto de reintentos de Waha y no
importa perderlo.

Funciones puras sobre una `Session` ya abierta (la abre y cierra
`ConversationStore` por cada operación, ver `whatsapp_bot_db.py`). Todas las
tablas cuelgan de `conversations` con `chat_id` como FK — `_ensure_conversation`
crea esa fila raíz antes de insertar en cualquier tabla hija.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.flows.whatsapp_bot_models import Conversation, ConversationFlags, ConversationIdentity, ConversationMessage, ConversationMeta


def _ensure_conversation(session: Session, chat_id: str) -> None:
    if session.get(Conversation, chat_id) is None:
        session.add(Conversation(chat_id=chat_id))
        session.flush()


def get_history(session: Session, chat_id: str, limit: int) -> list[dict[str, str]]:
    """Últimos `limit` turnos del chat, en orden cronológico."""
    rows = session.execute(
        select(ConversationMessage.role, ConversationMessage.content)
        .where(ConversationMessage.chat_id == chat_id)
        .order_by(ConversationMessage.id.desc())
        .limit(limit)
    ).all()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def get_full_history(session: Session, chat_id: str) -> list[dict[str, str]]:
    """Todo el historial del chat (sin recorte), en orden cronológico — para la vista de detalle del panel admin."""
    rows = session.execute(
        select(ConversationMessage.role, ConversationMessage.content, ConversationMessage.created_at)
        .where(ConversationMessage.chat_id == chat_id)
        .order_by(ConversationMessage.id.asc())
    ).all()
    return [{"role": role, "content": content, "created_at": created_at} for role, content, created_at in rows]


def list_chats(session: Session) -> list[dict[str, Any]]:
    """Un resumen por chat (último mensaje, deal_id, identidad confirmada), para la lista del panel admin.

    Ordenado por último mensaje descendente — los chats sin ningún mensaje
    en `conversation_messages` no aparecen (no hay nada que mostrar de
    ellos).
    """
    msg = ConversationMessage
    last_id_subq = select(msg.chat_id, func.max(msg.id).label("last_id")).group_by(msg.chat_id).subquery()
    count_subq = select(msg.chat_id, func.count(msg.id).label("message_count")).group_by(msg.chat_id).subquery()

    stmt = (
        select(
            msg.chat_id,
            msg.content,
            msg.created_at,
            count_subq.c.message_count,
            ConversationMeta.deal_id,
            ConversationIdentity.confirmed_name,
            ConversationIdentity.confirmed_phone,
        )
        .join(last_id_subq, (msg.chat_id == last_id_subq.c.chat_id) & (msg.id == last_id_subq.c.last_id))
        .join(count_subq, count_subq.c.chat_id == msg.chat_id)
        .outerjoin(ConversationMeta, ConversationMeta.chat_id == msg.chat_id)
        .outerjoin(ConversationIdentity, ConversationIdentity.chat_id == msg.chat_id)
        .order_by(msg.id.desc())
    )
    rows = session.execute(stmt).all()
    return [
        {
            "chat_id": chat_id,
            "last_content": last_content,
            "last_created_at": last_created_at,
            "message_count": message_count,
            "deal_id": deal_id,
            "confirmed_name": confirmed_name,
            "confirmed_phone": confirmed_phone,
        }
        for chat_id, last_content, last_created_at, message_count, deal_id, confirmed_name, confirmed_phone in rows
    ]


def add_turn(session: Session, chat_id: str, role: str, content: str, max_rows: int) -> None:
    """Guarda un turno y recorta el historial del chat a `max_rows` filas."""
    _ensure_conversation(session, chat_id)
    session.add(ConversationMessage(chat_id=chat_id, role=role, content=content, created_at=time.time()))
    session.flush()

    # MySQL no soporta `LIMIT` dentro de un subquery usado con `IN`/`NOT IN`
    # directamente ("LIMIT & IN/ALL/ANY/SOME subquery") — envolverlo en
    # `.subquery()` lo materializa como derived table, que sí soporta.
    keep_ids_subq = (
        select(ConversationMessage.id)
        .where(ConversationMessage.chat_id == chat_id)
        .order_by(ConversationMessage.id.desc())
        .limit(max_rows)
        .subquery()
    )
    session.execute(
        delete(ConversationMessage).where(
            ConversationMessage.chat_id == chat_id,
            ConversationMessage.id.notin_(select(keep_ids_subq.c.id)),
        )
    )
    session.commit()


def delete_chat(session: Session, chat_id: str) -> None:
    """Borra toda la data del chat (mensajes, deal_id, identidad, flags), incluida la fila raíz — usado por el panel admin."""
    session.execute(delete(ConversationMessage).where(ConversationMessage.chat_id == chat_id))
    session.execute(delete(ConversationMeta).where(ConversationMeta.chat_id == chat_id))
    session.execute(delete(ConversationFlags).where(ConversationFlags.chat_id == chat_id))
    session.execute(delete(ConversationIdentity).where(ConversationIdentity.chat_id == chat_id))
    session.execute(delete(Conversation).where(Conversation.chat_id == chat_id))
    session.commit()


def get_deal_id(session: Session, chat_id: str) -> str | None:
    row = session.get(ConversationMeta, chat_id)
    return row.deal_id if row else None


def set_deal_id(session: Session, chat_id: str, deal_id: str) -> None:
    _ensure_conversation(session, chat_id)
    row = session.get(ConversationMeta, chat_id)
    if row is None:
        session.add(ConversationMeta(chat_id=chat_id, deal_id=deal_id))
    else:
        row.deal_id = deal_id
    session.commit()


def clear_deal_id(session: Session, chat_id: str) -> None:
    session.execute(delete(ConversationMeta).where(ConversationMeta.chat_id == chat_id))
    session.commit()


def get_confirmed_identity(session: Session, chat_id: str) -> tuple[str | None, str | None]:
    row = session.get(ConversationIdentity, chat_id)
    return (row.confirmed_name, row.confirmed_phone) if row else (None, None)


def _get_or_create_identity(session: Session, chat_id: str) -> ConversationIdentity:
    _ensure_conversation(session, chat_id)
    row = session.get(ConversationIdentity, chat_id)
    if row is None:
        row = ConversationIdentity(chat_id=chat_id)
        session.add(row)
    return row


def set_confirmed_name(session: Session, chat_id: str, name: str) -> None:
    _get_or_create_identity(session, chat_id).confirmed_name = name
    session.commit()


def set_confirmed_phone(session: Session, chat_id: str, phone: str) -> None:
    _get_or_create_identity(session, chat_id).confirmed_phone = phone
    session.commit()


def get_pending_identity(session: Session, chat_id: str) -> tuple[str | None, str | None]:
    """Nombre/teléfono que el bot le propuso a la persona en su último mensaje, aún sin confirmar.

    Distinto de `confirmed_name`/`confirmed_phone`: sirve para que, si la
    persona responde con un simple "sí" a la pregunta de confirmación, el
    bot pueda promover estos valores a confirmados sin depender de que el
    LLM los repita en el JSON de ese turno.
    """
    row = session.get(ConversationIdentity, chat_id)
    return (row.pending_name, row.pending_phone) if row else (None, None)


def set_pending_name(session: Session, chat_id: str, name: str) -> None:
    _get_or_create_identity(session, chat_id).pending_name = name
    session.commit()


def set_pending_phone(session: Session, chat_id: str, phone: str) -> None:
    _get_or_create_identity(session, chat_id).pending_phone = phone
    session.commit()


def clear_pending_identity(session: Session, chat_id: str) -> None:
    row = session.get(ConversationIdentity, chat_id)
    if row is not None:
        row.pending_name = None
        row.pending_phone = None
        session.commit()


def get_explanation_sent(session: Session, chat_id: str) -> bool:
    row = session.get(ConversationFlags, chat_id)
    return bool(row.explanation_sent) if row else False


def set_explanation_sent(session: Session, chat_id: str) -> None:
    _ensure_conversation(session, chat_id)
    row = session.get(ConversationFlags, chat_id)
    if row is None:
        session.add(ConversationFlags(chat_id=chat_id, explanation_sent=True))
    else:
        row.explanation_sent = True
    session.commit()
