"""Endpoint interno que alimenta el <datalist> de ubicaciones del formulario de
Autorización de Corretaje (`app/forms/`) — no es una API pública para que
otros servicios la consuman, solo la usa la UI de ese formulario."""
from __future__ import annotations

from fastapi import APIRouter

from app.location_catalog.cache import get_cached_locations

router = APIRouter(tags=["Formularios"])


@router.get("/formularios/ubicaciones")
def list_location_suggestions() -> dict:
    return {
        "locations": [
            {"sector_code": location.sector_code, "display_label": location.display_label}
            for location in get_cached_locations()
        ]
    }
