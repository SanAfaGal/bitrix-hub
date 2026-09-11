"""`ConversationStore`: historial + cache de deal_id por chat, persistidos en MySQL; locks en memoria.

Separado de `whatsapp_bot.py` (límite de 500 líneas del repo) — mismo
motivo que `whatsapp_bot_llm.py`. `whatsapp_bot.py` reexporta
`ConversationStore` para no romper los imports existentes (tests incluidos).

El dedup de `message_id` (`already_processed`/`mark_processed`) es híbrido:
`_seen_message_ids` sigue siendo un dict en memoria, fast-path para el caso
normal (mensaje no duplicado, sin roundtrip a MySQL); `whatsapp_bot_store.
is_message_processed`/`mark_message_processed` son la red de seguridad en
MySQL que sobrevive a un restart del contenedor `api` — antes el dedup vivía
solo en memoria y un restart durante una resincronización de historial de
Waha podía hacer que el bot reprocesara y reenviara mensajes viejos.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.flows import whatsapp_bot_db as store_engine
from app.flows import whatsapp_bot_store as store_db

SEEN_MESSAGE_TTL_SECONDS = 600
RATE_LIMIT_COOLDOWN_SECONDS = 5  # Max 1 msg every 5 seconds per chat
# Purga de `_last_message_time`: una hora sin mensajes de un chat es de sobra
# para el cooldown de `RATE_LIMIT_COOLDOWN_SECONDS` — sin esto, ese dict
# crece sin límite, uno por cada chat distinto que haya escrito alguna vez.
LAST_MESSAGE_TIME_TTL_SECONDS = 3600


@dataclass
class ConversationStore:
    """Historial + cache de deal_id por chat, persistidos en MySQL; dedup de mensajes y locks en memoria.

    `engine=None` (default) crea un SQLite en memoria aislado por instancia
    — lo que quieren los tests. El singleton de proceso (`conversation_store`
    en `whatsapp_bot.py`) pasa el engine real de MySQL para sobrevivir a un
    restart/deploy.
    """

    max_history_turns: int = 6
    engine: Any = None
    _seen_message_ids: dict[str, float] = field(default_factory=dict)
    _last_message_time: dict[str, float] = field(default_factory=dict)
    _chat_locks: dict[str, threading.Lock] = field(default_factory=dict, repr=False)
    _chat_locks_guard: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _SessionLocal: Any = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        engine = self.engine or store_engine.build_sqlite_engine()
        self._SessionLocal = sessionmaker(bind=engine, future=True)

    def chat_lock(self, chat_id: str) -> threading.Lock:
        """Lock exclusivo por chat — serializa `process()` para que no se creen deals duplicados.

        Ver el docstring de `whatsapp_bot.py`: dos mensajes casi simultáneos
        del mismo chat corren en threads distintos y ambos pueden ver
        `deal_id is None` antes de que cualquiera lo cree, si no se
        serializan acá.

        Lock de memoria del proceso, no distribuido — asume un único worker
        de `uvicorn` (ver `docker-compose.yml`/`docker-compose.override.yml`,
        ninguno pasa `--workers`). Si el hub llega a correr con más de un
        worker/réplica, este lock deja de servir (cada proceso tendría el
        suyo) y hay que migrar a algo compartido (ej. `SELECT ... FOR UPDATE`
        en MySQL) para seguir evitando deals duplicados.

        No se purgan las entradas de `_chat_locks` con el tiempo: a
        diferencia de `_last_message_time`, borrar un lock mientras otro
        thread ya lo obtuvo de acá (antes de hacer `with lock:`) recrearía
        exactamente la condición de carrera que este lock evita. El costo de
        no purgar es acotado — un `threading.Lock` por cada chat distinto que
        haya escrito alguna vez, no por mensaje.
        """
        with self._chat_locks_guard:
            lock = self._chat_locks.get(chat_id)
            if lock is None:
                lock = threading.Lock()
                self._chat_locks[chat_id] = lock
            return lock

    def already_processed(self, message_id: str) -> bool:
        self._purge_expired_seen()
        if message_id in self._seen_message_ids:
            return True
        with self._SessionLocal() as session:
            return store_db.is_message_processed(session, message_id)

    def mark_processed(self, message_id: str) -> None:
        self._seen_message_ids[message_id] = time.monotonic()
        with self._SessionLocal() as session:
            store_db.mark_message_processed(session, message_id)

    def is_rate_limited(self, chat_id: str) -> bool:
        """Retorna True si el chat está en cooldown (más de 1 msg en últimos 5 seg)."""
        self._purge_expired_last_message_time()
        now = time.monotonic()
        if chat_id in self._last_message_time:
            elapsed = now - self._last_message_time[chat_id]
            if elapsed < RATE_LIMIT_COOLDOWN_SECONDS:
                return True
        return False

    def mark_message_received(self, chat_id: str) -> None:
        """Registra que recibimos un mensaje de este chat para rate limiting."""
        self._last_message_time[chat_id] = time.monotonic()

    def _purge_expired_seen(self) -> None:
        cutoff = time.monotonic() - SEEN_MESSAGE_TTL_SECONDS
        expired = [mid for mid, seen_at in self._seen_message_ids.items() if seen_at < cutoff]
        for mid in expired:
            del self._seen_message_ids[mid]

    def _purge_expired_last_message_time(self) -> None:
        cutoff = time.monotonic() - LAST_MESSAGE_TIME_TTL_SECONDS
        expired = [cid for cid, seen_at in self._last_message_time.items() if seen_at < cutoff]
        for cid in expired:
            del self._last_message_time[cid]

    def get_history(self, chat_id: str) -> list[dict[str, str]]:
        with self._SessionLocal() as session:
            return store_db.get_history(session, chat_id, self.max_history_turns * 2)

    def add_turn(self, chat_id: str, role: str, content: str, created_at: float | None = None) -> None:
        with self._SessionLocal() as session:
            store_db.add_turn(session, chat_id, role, content, created_at)

    def delete_chat(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.delete_chat(session, chat_id)

    def get_deal_id(self, chat_id: str) -> str | None:
        with self._SessionLocal() as session:
            return store_db.get_deal_id(session, chat_id)

    def set_deal_id(self, chat_id: str, deal_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.set_deal_id(session, chat_id, deal_id)

    def clear_deal_id(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.clear_deal_id(session, chat_id)

    def get_confirmed_identity(self, chat_id: str) -> tuple[str | None, str | None]:
        with self._SessionLocal() as session:
            return store_db.get_confirmed_identity(session, chat_id)

    def set_confirmed_identity(self, chat_id: str, name: str, phone: str) -> None:
        with self._SessionLocal() as session:
            store_db.set_confirmed_identity(session, chat_id, name, phone)

    def get_explanation_sent(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.get_explanation_sent(session, chat_id)

    def set_explanation_sent(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.set_explanation_sent(session, chat_id)

    def get_authorization_link_sent(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.get_authorization_link_sent(session, chat_id)

    def set_authorization_link_sent(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.set_authorization_link_sent(session, chat_id)

    def get_zone_asked(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.get_zone_asked(session, chat_id)

    def set_zone_asked(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.set_zone_asked(session, chat_id)

    def get_zone_in_coverage(self, chat_id: str) -> bool | None:
        with self._SessionLocal() as session:
            return store_db.get_zone_in_coverage(session, chat_id)

    def set_zone_in_coverage(self, chat_id: str, in_coverage: bool) -> None:
        with self._SessionLocal() as session:
            store_db.set_zone_in_coverage(session, chat_id, in_coverage)

    def chat_exists(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.chat_exists(session, chat_id)

    def get_bot_enabled(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.get_bot_enabled(session, chat_id)

    def get_bot_enabled_reason(self, chat_id: str) -> str | None:
        with self._SessionLocal() as session:
            return store_db.get_bot_enabled_reason(session, chat_id)

    def set_bot_enabled(self, chat_id: str, enabled: bool, reason: str | None = None) -> None:
        with self._SessionLocal() as session:
            store_db.set_bot_enabled(session, chat_id, enabled, reason)

    def get_full_history(self, chat_id: str) -> list[dict[str, str]]:
        with self._SessionLocal() as session:
            return store_db.get_full_history(session, chat_id)

    def get_history_seeded(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.get_history_seeded(session, chat_id)

    def set_history_seeded(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.set_history_seeded(session, chat_id)

    def has_assistant_turn(self, chat_id: str) -> bool:
        with self._SessionLocal() as session:
            return store_db.has_assistant_turn(session, chat_id)

    def clear_messages(self, chat_id: str) -> None:
        with self._SessionLocal() as session:
            store_db.clear_messages(session, chat_id)

    def list_chats(self) -> list[dict[str, Any]]:
        with self._SessionLocal() as session:
            return store_db.list_chats(session)
