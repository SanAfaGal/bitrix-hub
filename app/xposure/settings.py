"""Configuración de variables de entorno para la integración con Xposure."""
from __future__ import annotations

import os

from dotenv import load_dotenv


def load_xposure_settings() -> tuple[str, str, str]:
    """Carga y valida las variables de entorno requeridas para Xposure."""
    load_dotenv()

    base_url = (os.getenv("XPOSURE_BASE_URL") or "").strip()
    username = (os.getenv("XPOSURE_USERNAME") or "").strip()
    password = (os.getenv("XPOSURE_PASSWORD") or "").strip()

    missing = [name for name, value in (
        ("XPOSURE_BASE_URL", base_url),
        ("XPOSURE_USERNAME", username),
        ("XPOSURE_PASSWORD", password),
    ) if not value]

    if missing:
        raise RuntimeError("Faltan variables de entorno: " + ", ".join(missing))

    return base_url.rstrip("/"), username, password
