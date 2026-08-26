"""Persistencia en SQLite del historial de conversación del bot de WhatsApp.

Solo el historial de turnos y el cache de `deal_id` por chat viven acá —
sobreviven a un restart/deploy del proceso, a diferencia del dedup de
mensajes (`ConversationStore._seen_message_ids` en `whatsapp_bot.py`), que
sigue en memoria porque es solo un TTL corto de reintentos de Waha y no
importa perderlo. Funciones puras sobre una `sqlite3.Connection` ya abierta
(la abre y mantiene `ConversationStore`), sin ORM — consistente con el
resto del repo.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


def init_db(db_path: str) -> sqlite3.Connection:
    """Abre (creando si hace falta) la conexión y el esquema de la base de historial."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_chat_id ON conversation_messages (chat_id, id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_meta (
            chat_id TEXT PRIMARY KEY,
            deal_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_identity (
            chat_id TEXT PRIMARY KEY,
            confirmed_name TEXT,
            confirmed_phone TEXT
        )
        """
    )
    conn.commit()
    return conn


def get_history(conn: sqlite3.Connection, chat_id: str, limit: int) -> list[dict[str, str]]:
    """Últimos `limit` turnos del chat, en orden cronológico."""
    rows = conn.execute(
        "SELECT role, content FROM conversation_messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def add_turn(conn: sqlite3.Connection, chat_id: str, role: str, content: str, max_rows: int) -> None:
    """Guarda un turno y recorta el historial del chat a `max_rows` filas."""
    conn.execute(
        "INSERT INTO conversation_messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, time.time()),
    )
    conn.execute(
        """
        DELETE FROM conversation_messages
        WHERE chat_id = ? AND id NOT IN (
            SELECT id FROM conversation_messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?
        )
        """,
        (chat_id, chat_id, max_rows),
    )
    conn.commit()


def get_deal_id(conn: sqlite3.Connection, chat_id: str) -> str | None:
    row = conn.execute("SELECT deal_id FROM conversation_meta WHERE chat_id = ?", (chat_id,)).fetchone()
    return row[0] if row else None


def set_deal_id(conn: sqlite3.Connection, chat_id: str, deal_id: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_meta (chat_id, deal_id) VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET deal_id = excluded.deal_id
        """,
        (chat_id, deal_id),
    )
    conn.commit()


def clear_deal_id(conn: sqlite3.Connection, chat_id: str) -> None:
    conn.execute("DELETE FROM conversation_meta WHERE chat_id = ?", (chat_id,))
    conn.commit()


def get_confirmed_identity(conn: sqlite3.Connection, chat_id: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT confirmed_name, confirmed_phone FROM conversation_identity WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def set_confirmed_name(conn: sqlite3.Connection, chat_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_identity (chat_id, confirmed_name) VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET confirmed_name = excluded.confirmed_name
        """,
        (chat_id, name),
    )
    conn.commit()


def set_confirmed_phone(conn: sqlite3.Connection, chat_id: str, phone: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_identity (chat_id, confirmed_phone) VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET confirmed_phone = excluded.confirmed_phone
        """,
        (chat_id, phone),
    )
    conn.commit()
