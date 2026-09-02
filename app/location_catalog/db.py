"""Engine SQLAlchemy para el DWH de Mobilia (solo lectura).

`create_engine` no abre conexión de red hasta la primera consulta (pool
lazy), así que importar este módulo es seguro incluso sin la base
disponible — el error real solo aparece cuando `client.py` intenta usarla, y
ese módulo lo captura y cae a lista vacía.

`charset="utf8mb4"` es obligatorio: sin él, las tildes llegan corruptas
(confirmado en vivo — "Bogotá" llega como "Bogot�" con el charset por
defecto de la conexión).
"""
from __future__ import annotations

from sqlalchemy import create_engine

from app.location_catalog.settings import load_location_catalog_settings


def _build_engine():
    settings = load_location_catalog_settings()
    url = (
        f"mysql+pymysql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "charset": "utf8mb4"},
        future=True,
    )


engine = _build_engine()
