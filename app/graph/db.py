"""Sesión SQLAlchemy para la tabla `graph_processed_messages`.

Comparte el pool MySQL de `app.message_templates.db` (misma base
`bitrix_hub`) en vez de abrir una conexión propia — es la misma base de
datos, no hace falta un segundo pool (mismo criterio que
`app/flows/whatsapp_bot_db.py`).
"""
from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.message_templates.db import engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
