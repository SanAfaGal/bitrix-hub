"""Dependencias de FastAPI para la integración con Xposure."""
from __future__ import annotations

from fastapi import HTTPException

from app.xposure.client import XposureClient
from app.xposure.settings import load_xposure_settings


def get_xposure_client() -> XposureClient:
    """Crea y autentica un cliente de Xposure listo para usar.

    Errores de configuración o de login se traducen a 502 acá, en el único
    lugar donde se crea el cliente — las rutas no necesitan repetir el
    try/except para esta parte.
    """
    try:
        base_url, username, password = load_xposure_settings()
        client = XposureClient(base_url, username, password)
        client.login()
        return client
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
