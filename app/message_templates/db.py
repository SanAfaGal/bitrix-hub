"""Engine/sesión SQLAlchemy para la base MySQL de plantillas de mensajes.

`create_engine` no abre conexión de red hasta la primera consulta (pool
lazy), así que importar este módulo es seguro incluso sin MySQL disponible
(tests, entornos sin `.env` completo) — el error real solo aparece cuando
`store.py` intenta usarlo, y ese módulo lo captura y cae a los defaults.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.message_templates.settings import load_message_templates_settings


def _build_engine():
    settings = load_message_templates_settings()
    url = (
        f"mysql+pymysql://{settings.user}:{settings.password}"
        f"@{settings.host}:{settings.port}/{settings.database}"
    )
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5}, future=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
