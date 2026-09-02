"""Lectura del catálogo de ubicaciones (sectores/ciudades) desde el DWH de Mobilia.

Nunca lanza por falla de red: loguea y devuelve lista vacía, como el resto de
los `client.py` de este repo (ver CLAUDE.md) — la vista `view_name` ya viene
separada en columnas del lado del DWH, así que acá no hace falta el parseo
de un campo de texto empacado que sí necesitó un trabajo previo sobre
Bitrix (ver Procesos-Automatizacion-Bitrix/scripts). El texto que se
muestra en la UI sigue necesitando limpieza de formato y dedup (sector y
zona muchas veces repiten el nombre de la ciudad, ej. sector "SALAMINA" +
ciudad "Salamina") — para eso se reutiliza `normalize.build_location_label`,
portado de ese mismo script de referencia.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.location_catalog import db
from app.location_catalog.normalize import build_location_label, normalize_key
from app.location_catalog.settings import load_location_catalog_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocationSuggestion:
    sector_code: str
    display_label: str


def fetch_all_locations() -> list[LocationSuggestion]:
    view_name = load_location_catalog_settings().view_name
    query = text(
        f"SELECT sector_code, sector, zona, ciudad, departamento, pais FROM {view_name}"  # noqa: S608 — view_name es config del operador, no input de request
    )
    try:
        with db.engine.connect() as connection:
            rows = connection.execute(query).all()
    except SQLAlchemyError:
        logger.exception("No se pudo leer el catálogo de ubicaciones del DWH de Mobilia")
        return []

    suggestions = [
        LocationSuggestion(
            sector_code=row.sector_code,
            display_label=build_location_label(row.sector, row.zona, row.ciudad, row.departamento, row.pais),
        )
        for row in rows
    ]
    return _dedupe_by_display_label(suggestions)


def _dedupe_by_display_label(suggestions: list[LocationSuggestion]) -> list[LocationSuggestion]:
    """Distintos sector_code pueden terminar con el mismo texto tras
    `build_location_label` (ej. dos sectores sin nombre propio en el mismo
    "Neiva, Huila") — sin esto, esa ubicación aparecería dos veces idéntica
    en el desplegable. Se queda con la primera aparición (mismo orden que
    trae la vista); el sector_code descartado no se pierde en la base, solo
    no se ofrece como sugerencia repetida."""
    seen: set[str] = set()
    result = []
    for suggestion in suggestions:
        key = normalize_key(suggestion.display_label)
        if key in seen:
            continue
        seen.add(key)
        result.append(suggestion)
    return result
