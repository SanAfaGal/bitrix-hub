"""Configuración de qué CRM está activo."""
from __future__ import annotations

import os

from dotenv import load_dotenv


def load_crm_settings() -> str:
    """Carga y valida el proveedor de CRM activo (CRM_PROVIDER)."""
    load_dotenv()

    provider = (os.getenv("CRM_PROVIDER") or "").strip().lower()

    if not provider:
        raise RuntimeError("Falta variable de entorno: CRM_PROVIDER")

    return provider
