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


def load_bitrix_webhook_secret() -> str | None:
    """Secreto compartido opcional para los webhooks de `/webhook/deal-*` (mismo patrón que
    `WHATSAPP_WEBHOOK_SECRET` en app/waha/settings.py). Configurar la regla de automatización
    de Bitrix para mandar `?secret=<este valor>` en la URL del webhook; si no está seteado, no
    se exige (no usar así en producción)."""
    load_dotenv()
    return (os.getenv("BITRIX_WEBHOOK_SECRET") or "").strip() or None
