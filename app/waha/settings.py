"""Configuración de variables de entorno para la integración con Waha (WhatsApp)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class WahaSettings:
    base_url: str
    api_key: str | None
    session: str
    webhook_secret: str | None = None


def load_waha_settings() -> WahaSettings:
    """Carga y valida la configuración de Waha."""
    load_dotenv()

    base_url = (os.getenv("WAHA_BASE_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Falta variable de entorno: WAHA_BASE_URL")

    api_key = (os.getenv("WAHA_API_KEY") or "").strip() or None
    session = (os.getenv("WAHA_SESSION") or "default").strip()
    webhook_secret = (os.getenv("WHATSAPP_WEBHOOK_SECRET") or "").strip() or None

    return WahaSettings(base_url=base_url, api_key=api_key, session=session, webhook_secret=webhook_secret)
