"""Configuración de variables de entorno para el catálogo de ubicaciones (DWH de Mobilia).

Base de datos externa, distinta de la MySQL propia de la app (ver
`app/message_templates/settings.py`) — no comparte prefijo de variables de
entorno con esa, para no confundir ambas conexiones.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class LocationCatalogSettings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    view_name: str


def load_location_catalog_settings() -> LocationCatalogSettings:
    """Carga la configuración de conexión al DWH de Mobilia — sin defaults de
    host/usuario/password: es una red externa que la app no controla, así que
    una variable faltante debe traducirse en una conexión que falla (y cae al
    fallback de `client.py`), no en apuntar por accidente a otro lado."""
    load_dotenv()

    return LocationCatalogSettings(
        db_host=(os.getenv("MOBILIA_DWH_HOST") or "").strip(),
        db_port=int((os.getenv("MOBILIA_DWH_PORT") or "3306").strip()),
        db_name=(os.getenv("MOBILIA_DWH_DATABASE") or "").strip(),
        db_user=(os.getenv("MOBILIA_DWH_USER") or "").strip(),
        db_password=os.getenv("MOBILIA_DWH_PASSWORD") or "",
        view_name=(os.getenv("MOBILIA_DWH_VIEW") or "cat_mobilia_sectores").strip(),
    )
