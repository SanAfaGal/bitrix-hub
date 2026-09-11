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
    session_https_only: bool = True


def load_admin_settings() -> AdminSettings:
    """Carga usuario/clave único compartido y el secreto de sesión del panel admin.

    `session_https_only` (default `True`) fuerza la cookie de sesión a viajar solo por HTTPS —
    el caso normal en producción (VPS detrás de un reverse proxy con TLS, ver README). Se puede
    apagar con `ADMIN_SESSION_HTTPS_ONLY=false` para desarrollo local sin TLS (ej. `docker
    compose up` accediendo por `http://localhost`)."""
    load_dotenv()

    username = (os.getenv("ADMIN_USERNAME") or "").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    session_secret = (os.getenv("ADMIN_SESSION_SECRET") or "").strip()
    session_https_only = (os.getenv("ADMIN_SESSION_HTTPS_ONLY") or "true").strip().lower() not in ("0", "false", "no")

    if not username or not password:
        raise RuntimeError("Faltan variables de entorno: ADMIN_USERNAME / ADMIN_PASSWORD")
    if not session_secret:
        raise RuntimeError("Falta variable de entorno: ADMIN_SESSION_SECRET")

    return AdminSettings(
        username=username, password=password, session_secret=session_secret, session_https_only=session_https_only
    )
