"""Configuración de variables de entorno compartida por los flujos multi-integración."""
from __future__ import annotations

import os

from dotenv import load_dotenv


def load_public_base_url() -> str:
    """Carga la URL pública base del hub (sin `/` final) usada para armar enlaces enviados al cliente."""
    load_dotenv()

    base_url = (os.getenv("HUB_PUBLIC_BASE_URL") or "").strip()

    if not base_url:
        raise RuntimeError("Falta variable de entorno: HUB_PUBLIC_BASE_URL")

    return base_url.rstrip("/")
