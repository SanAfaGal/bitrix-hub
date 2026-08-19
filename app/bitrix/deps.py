"""Dependencias de FastAPI para la integración con Bitrix."""
from __future__ import annotations

from app.bitrix.client import BitrixClient
from app.bitrix.settings import load_bitrix_settings


def get_bitrix_client() -> BitrixClient:
    """Crea un cliente de Bitrix a partir de la configuración del webhook."""
    webhook_url = load_bitrix_settings()
    return BitrixClient(webhook_url)
