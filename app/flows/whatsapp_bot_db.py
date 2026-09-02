"""Engine/sesión SQLAlchemy para las tablas de conversación del bot de WhatsApp.

Comparte el pool MySQL de `app.message_templates.db` (misma base
`bitrix_hub`) en vez de abrir una conexión propia — es la misma base de
datos, no hace falta un segundo pool.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flows.whatsapp_bot_models import Base
from app.message_templates.db import engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def build_sqlite_engine(url: str = "sqlite:///:memory:") -> Engine:
    """Motor SQLite standalone, aislado del MySQL de producción — usado por `ConversationStore` por defecto (tests).

    `StaticPool` en el caso `:memory:` es necesario: sin él, cada conexión
    que SQLAlchemy saca del pool abriría una base en memoria distinta (vacía)
    en vez de compartir la misma — con un archivo real no hace falta.
    """
    connect_args: dict[str, object] = {"check_same_thread": False}
    kwargs: dict[str, object] = {"future": True, "connect_args": connect_args}
    if url == "sqlite:///:memory:":
        kwargs["poolclass"] = StaticPool
    test_engine = create_engine(url, **kwargs)
    Base.metadata.create_all(test_engine)
    return test_engine
