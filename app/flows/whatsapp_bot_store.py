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
from typing import Any


def init_db(db_path: str) -> sqlite3.Connection:
    """Abre (creando si hace falta) la conexión y el esquema de la base de historial."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
        CREATE TABLE IF NOT EXISTS conversation_flags (
            chat_id TEXT PRIMARY KEY,
            explanation_sent INTEGER NOT NULL DEFAULT 0
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
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(conversation_identity)")}
    if "pending_name" not in existing_columns:
        conn.execute("ALTER TABLE conversation_identity ADD COLUMN pending_name TEXT")
    if "pending_phone" not in existing_columns:
        conn.execute("ALTER TABLE conversation_identity ADD COLUMN pending_phone TEXT")
    conn.commit()
    return conn


def get_history(conn: sqlite3.Connection, chat_id: str, limit: int) -> list[dict[str, str]]:
    """Últimos `limit` turnos del chat, en orden cronológico."""
    rows = conn.execute(
        "SELECT role, content FROM conversation_messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def get_full_history(conn: sqlite3.Connection, chat_id: str) -> list[dict[str, str]]:
    """Todo el historial del chat (sin recorte), en orden cronológico — para la vista de detalle del panel admin."""
    rows = conn.execute(
        "SELECT role, content, created_at FROM conversation_messages WHERE chat_id = ? ORDER BY id ASC",
        (chat_id,),
    ).fetchall()
    return [{"role": role, "content": content, "created_at": created_at} for role, content, created_at in rows]


def list_chats(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Un resumen por chat (último mensaje, deal_id, identidad confirmada), para la lista del panel admin.

    Ordenado por último mensaje descendente — los chats sin ningún mensaje
    en `conversation_messages` no aparecen (no hay nada que mostrar de
    ellos).
    """
    rows = conn.execute(
        """
        SELECT
            m.chat_id,
            m.last_content,
            m.last_created_at,
            m.message_count,
            meta.deal_id,
            identity.confirmed_name,
            identity.confirmed_phone
        FROM (
            SELECT
                chat_id,
                content AS last_content,
                created_at AS last_created_at,
                id AS last_id,
                (SELECT COUNT(*) FROM conversation_messages c2 WHERE c2.chat_id = c1.chat_id) AS message_count
            FROM conversation_messages c1
            WHERE id IN (SELECT MAX(id) FROM conversation_messages GROUP BY chat_id)
        ) m
        LEFT JOIN conversation_meta meta ON meta.chat_id = m.chat_id
        LEFT JOIN conversation_identity identity ON identity.chat_id = m.chat_id
        ORDER BY m.last_id DESC
        """
    ).fetchall()
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


def get_pending_identity(conn: sqlite3.Connection, chat_id: str) -> tuple[str | None, str | None]:
    """Nombre/teléfono que el bot le propuso a la persona en su último mensaje, aún sin confirmar.

    Distinto de `confirmed_name`/`confirmed_phone`: sirve para que, si la
    persona responde con un simple "sí" a la pregunta de confirmación, el
    bot pueda promover estos valores a confirmados sin depender de que el
    LLM los repita en el JSON de ese turno.
    """
    row = conn.execute(
        "SELECT pending_name, pending_phone FROM conversation_identity WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def set_pending_name(conn: sqlite3.Connection, chat_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_identity (chat_id, pending_name) VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET pending_name = excluded.pending_name
        """,
        (chat_id, name),
    )
    conn.commit()


def set_pending_phone(conn: sqlite3.Connection, chat_id: str, phone: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_identity (chat_id, pending_phone) VALUES (?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET pending_phone = excluded.pending_phone
        """,
        (chat_id, phone),
    )
    conn.commit()


def clear_pending_identity(conn: sqlite3.Connection, chat_id: str) -> None:
    conn.execute(
        "UPDATE conversation_identity SET pending_name = NULL, pending_phone = NULL WHERE chat_id = ?",
        (chat_id,),
    )
    conn.commit()


def get_explanation_sent(conn: sqlite3.Connection, chat_id: str) -> bool:
    row = conn.execute(
        "SELECT explanation_sent FROM conversation_flags WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return bool(row[0]) if row else False


def set_explanation_sent(conn: sqlite3.Connection, chat_id: str) -> None:
    conn.execute(
        """
        INSERT INTO conversation_flags (chat_id, explanation_sent) VALUES (?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET explanation_sent = 1
        """,
        (chat_id,),
    )
    conn.commit()
