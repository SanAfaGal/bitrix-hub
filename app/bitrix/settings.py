"""Configuración de variables de entorno para la integración con Bitrix."""
from __future__ import annotations

import os

from dotenv import load_dotenv


def load_bitrix_settings() -> str:
    """Carga y valida la URL del webhook entrante de Bitrix."""
    load_dotenv()

    webhook_url = (os.getenv("BITRIX_WEBHOOK_URL") or "").strip()

    if not webhook_url:
        raise RuntimeError("Falta variable de entorno: BITRIX_WEBHOOK_URL")

    return webhook_url
