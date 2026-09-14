"""Dependencias de FastAPI para la integración con Xposure."""
from __future__ import annotations

import threading

from fastapi import HTTPException

from app.xposure.client import XposureClient
from app.xposure.settings import load_xposure_settings

# Cliente autenticado compartido entre requests — loguearse en Xposure son 2
# round trips (GET /Login + POST /DoLogin); hacerlo en cada request (incluido
# cada item de un lote en /properties/bulk) es puro desperdicio. Se
# reautentica solo si el login falla o si una búsqueda detecta la sesión
# caída (ver XposureClient.login/search_property).
_client: XposureClient | None = None
_client_lock = threading.Lock()


def get_xposure_client() -> XposureClient:
    """Devuelve un cliente de Xposure autenticado, reutilizando sesión entre requests.

    Errores de configuración o de login se traducen a 502 acá, en el único
    lugar donde se crea el cliente — las rutas no necesitan repetir el
    try/except para esta parte.
    """
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            base_url, username, password = load_xposure_settings()
            client = XposureClient(base_url, username, password)
            client.login()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        _client = client
        return _client


def reset_xposure_client() -> None:
    """Descarta el cliente cacheado — llamar cuando una operación detecta sesión caída
    (redirect a /Login) para forzar reautenticación en el siguiente `get_xposure_client()`."""
    global _client
    with _client_lock:
        _client = None
