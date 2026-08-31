"""Configuración de variables de entorno para el panel admin."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AdminSettings:
    username: str
    password: str
    session_secret: str


def load_admin_settings() -> AdminSettings:
    """Carga usuario/clave único compartido y el secreto de sesión del panel admin."""
    load_dotenv()

    username = (os.getenv("ADMIN_USERNAME") or "").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    session_secret = (os.getenv("ADMIN_SESSION_SECRET") or "").strip()

    if not username or not password:
        raise RuntimeError("Faltan variables de entorno: ADMIN_USERNAME / ADMIN_PASSWORD")
    if not session_secret:
        raise RuntimeError("Falta variable de entorno: ADMIN_SESSION_SECRET")

    return AdminSettings(username=username, password=password, session_secret=session_secret)
