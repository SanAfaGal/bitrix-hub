"""Dependencias de FastAPI para la integración con Microsoft Graph."""
from __future__ import annotations

from fastapi import HTTPException

from app.graph.client import GraphClient
from app.graph.settings import load_graph_settings


def get_graph_client() -> GraphClient:
    """Crea un cliente de Microsoft Graph listo para usar.

    Errores de configuración se traducen a 502 acá, en el único lugar donde
    se crea el cliente — las rutas no necesitan repetir el try/except.
    """
    try:
        tenant_id, client_id, client_secret, mailbox = load_graph_settings()
        return GraphClient(tenant_id, client_id, client_secret, mailbox)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
