"""Persistencia en MySQL (SQLAlchemy) del historial y estado de conversación del bot de WhatsApp.

Todo lo 1:1 por chat (identidad, deal_id, estado de la explicación) vive en
`Conversation`; el historial de turnos vive en `ConversationMessage` (1:N).
Distinto del dedup de mensajes (`ConversationStore._seen_message_ids` en
`whatsapp_bot.py`), que sigue en memoria porque es solo un TTL corto de
reintentos de Waha y no importa perderlo.

Funciones puras sobre una `Session` ya abierta (la abre y cierra
`ConversationStore` por cada operación, ver `whatsapp_bot_db.py`).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.flows.whatsapp_bot_models import Conversation, ConversationMessage


def _get_by_chat_id(session: Session, chat_id: str) -> Conversation | None:
    """`chat_id` ya no es la PK de `leads` (ver whatsapp_bot_models.py) — reemplaza
    los `session.get(Conversation, chat_id)` de antes, que buscaban por PK."""
    return session.execute(select(Conversation).where(Conversation.chat_id == chat_id)).scalar_one_or_none()


def _get_or_create(session: Session, chat_id: str) -> Conversation:
    row = _get_by_chat_id(session, chat_id)
    if row is None:
        row = Conversation(chat_id=chat_id, channel="whatsapp", created_at=datetime.now(timezone.utc))
        session.add(row)
        session.flush()
    return row


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
    """Resumen de todos los leads (WhatsApp + correo) para la lista del panel admin.

    Se arman por separado (formas muy distintas de "último mensaje": un
    turno de chat real vs. el resultado de procesar un correo) y se
    combinan ordenados por `last_created_at` descendente.
    """
    whatsapp_chats = _list_whatsapp_chats(session)
    email_leads = _list_email_leads(session)
    combined = whatsapp_chats + email_leads
    combined.sort(key=lambda c: c["last_created_at"] or 0, reverse=True)
    return combined


def _list_whatsapp_chats(session: Session) -> list[dict[str, Any]]:
    """Un resumen por chat (último mensaje, deal_id, identidad confirmada).

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
            Conversation.deal_id,
            Conversation.name,
            Conversation.phone,
        )
        .join(last_id_subq, (msg.chat_id == last_id_subq.c.chat_id) & (msg.id == last_id_subq.c.last_id))
        .join(count_subq, count_subq.c.chat_id == msg.chat_id)
        .outerjoin(Conversation, Conversation.chat_id == msg.chat_id)
        .order_by(msg.id.desc())
    )
    rows = session.execute(stmt).all()
    return [
        {
            "chat_id": chat_id,
            "email_tracking_id": None,
            "channel": "whatsapp",
            "last_content": last_content,
            "last_created_at": last_created_at,
            "message_count": message_count,
            "deal_id": deal_id,
            "confirmed_name": name,
            "confirmed_phone": phone,
        }
        for chat_id, last_content, last_created_at, message_count, deal_id, name, phone in rows
    ]


def _list_email_leads(session: Session) -> list[dict[str, Any]]:
    """Un resumen por lead de correo (formulario web) — nunca tienen `conversation_messages`."""
    rows = session.execute(
        select(Conversation).where(Conversation.channel == "email").order_by(Conversation.created_at.desc())
    ).scalars().all()
    return [
        {
            "chat_id": None,
            "email_tracking_id": row.email_tracking_id,
            "channel": "email",
            "last_content": _email_lead_preview(row),
            "last_created_at": row.created_at.timestamp() if row.created_at else None,
            "message_count": 0,
            "deal_id": row.deal_id,
            "confirmed_name": row.name,
            "confirmed_phone": row.phone,
        }
        for row in rows
    ]


def _email_lead_preview(row: Conversation) -> str:
    if row.status == "created":
        return "Lead de formulario web — negociación creada"
    if row.status == "skipped":
        return f"Lead de formulario web — omitido ({row.detail})"
    return f"Lead de formulario web — error ({row.detail})"


def add_turn(session: Session, chat_id: str, role: str, content: str) -> None:
    """Guarda un turno. No recorta nada — `conversation_messages` guarda la conversación
    completa para siempre (auditoría, panel admin); el recorte a cuántos turnos recientes
    se le mandan al LLM como contexto vive en la lectura (`get_history(limit)`), no acá."""
    _get_or_create(session, chat_id)
    session.add(ConversationMessage(chat_id=chat_id, role=role, content=content, created_at=time.time()))
    session.commit()


def delete_chat(session: Session, chat_id: str) -> None:
    """Borra toda la data del chat (mensajes + fila de conversación) — usado por el panel admin."""
    session.execute(delete(ConversationMessage).where(ConversationMessage.chat_id == chat_id))
    session.execute(delete(Conversation).where(Conversation.chat_id == chat_id))
    session.commit()


def get_deal_id(session: Session, chat_id: str) -> str | None:
    row = _get_by_chat_id(session, chat_id)
    return row.deal_id if row else None


def set_deal_id(session: Session, chat_id: str, deal_id: str) -> None:
    row = _get_or_create(session, chat_id)
    row.deal_id = deal_id
    session.commit()


def clear_deal_id(session: Session, chat_id: str) -> None:
    row = _get_by_chat_id(session, chat_id)
    if row is not None:
        row.deal_id = None
        session.commit()


def get_confirmed_identity(session: Session, chat_id: str) -> tuple[str | None, str | None]:
    row = _get_by_chat_id(session, chat_id)
    if row is None:
        return (None, None)
    return (row.name, row.phone)


def set_confirmed_identity(session: Session, chat_id: str, name: str, phone: str) -> None:
    """Guarda nombre y teléfono juntos — solo se llama una vez el LLM ya tiene ambos
    confirmados (ver `_apply_confirmed_identity` en whatsapp_bot.py), nunca con uno solo."""
    row = _get_or_create(session, chat_id)
    row.name = name
    row.phone = phone
    session.commit()


def get_explanation_sent(session: Session, chat_id: str) -> bool:
    row = _get_by_chat_id(session, chat_id)
    return bool(row.explanation_sent) if row else False


def set_explanation_sent(session: Session, chat_id: str) -> None:
    row = _get_or_create(session, chat_id)
    row.explanation_sent = True
    session.commit()


def get_explanation_offered(session: Session, chat_id: str) -> bool:
    row = _get_by_chat_id(session, chat_id)
    return bool(row.explanation_offered) if row else False


def set_explanation_offered(session: Session, chat_id: str) -> None:
    row = _get_or_create(session, chat_id)
    row.explanation_offered = True
    session.commit()


def get_authorization_link_sent(session: Session, chat_id: str) -> bool:
    row = _get_by_chat_id(session, chat_id)
    return bool(row.authorization_link_sent) if row else False


def set_authorization_link_sent(session: Session, chat_id: str) -> None:
    row = _get_or_create(session, chat_id)
    row.authorization_link_sent = True
    session.commit()
