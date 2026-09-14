"""Dependencias de FastAPI para la integración con Waha."""
from __future__ import annotations

from fastapi import HTTPException

from app.waha.client import WahaClient
from app.waha.settings import load_waha_settings


def get_waha_client() -> WahaClient:
    """Crea un cliente de Waha a partir de la configuración de entorno.

    Una sola instancia/una sola sesión (`WAHA_SESSION`) por ahora — una segunda línea de
    WhatsApp en el futuro sería una segunda instancia de `WahaSettings`/`WahaClient` con su
    propio `session`, no un rediseño de esta función ni del panel admin que la usa."""
    try:
        settings = load_waha_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return WahaClient(settings)
