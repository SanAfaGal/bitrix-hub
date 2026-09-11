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

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from app.location_catalog import db
from app.location_catalog.normalize import build_location_label, normalize_key
from app.location_catalog.settings import load_location_catalog_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocationSuggestion:
    sector_code: str
    display_label: str


@dataclass(frozen=True)
class Sector:
    sector_code: str
    sector: str
    zona: str
    ciudad: str
    departamento: str
    pais: str
    cobertura: bool


def fetch_all_sectores() -> list[Sector] | None:
    """Lista completa de sectores para el admin de cobertura de ventas — sin el
    dedupe de `fetch_all_locations` (acá cada `sector_code` se administra por
    separado, aunque dos terminen con el mismo texto de ubicación).

    `None` cuando falla la consulta (DWH caído, vista mal configurada) —
    deliberadamente distinto de `[]` (vista real sin filas). `run_sync`
    (`app.location_catalog.sector_sync`) necesita esa distinción: confundir
    "fuente caída" con "catálogo vacío" hacía que reportara TODOS los
    sectores de Bitrix como "ya no están en la fuente" y terminara con éxito
    pese al fallo real."""
    view_name = load_location_catalog_settings().view_name
    query = text(
        f"SELECT sector_code, sector, zona, ciudad, departamento, pais, cobertura_ventas "  # noqa: S608 — view_name es config del operador
        f"FROM {view_name} ORDER BY ciudad, sector"
    )
    try:
        with db.engine.connect() as connection:
            rows = connection.execute(query).all()
    except SQLAlchemyError:
        logger.exception("No se pudo leer el catálogo de sectores del DWH de Mobilia")
        return None

    return [
        Sector(
            sector_code=row.sector_code,
            sector=row.sector,
            zona=row.zona,
            ciudad=row.ciudad,
            departamento=row.departamento,
            pais=row.pais,
            cobertura=bool(row.cobertura_ventas),
        )
        for row in rows
    ]


def set_cobertura(sector_codes: list[str], covered: bool) -> bool:
    """Activa/desactiva `cobertura_ventas` para los `sector_code` dados, en batch.

    Primer write de este repo contra `mobilia_dwh` — hasta ahora todo acceso acá
    era de solo lectura. Igual que el resto del archivo, nunca lanza: loguea y
    devuelve `False` si la conexión o el UPDATE fallan."""
    if not sector_codes:
        return True

    view_name = load_location_catalog_settings().view_name
    query = text(
        f"UPDATE {view_name} SET cobertura_ventas = :covered WHERE sector_code IN :codes"  # noqa: S608 — view_name es config del operador
    ).bindparams(bindparam("codes", expanding=True))
    try:
        with db.engine.begin() as connection:
            connection.execute(query, {"covered": covered, "codes": sector_codes})
    except SQLAlchemyError:
        logger.exception("No se pudo actualizar cobertura_ventas en el DWH de Mobilia")
        return False
    return True


def get_sector_coverage(sector_code: str) -> bool | None:
    """None = no se pudo determinar (sector_code no existe o falló la consulta) —
    fresca siempre, nunca cacheada ni servida por fetch_all_locations()/
    get_cached_locations(): ese cache dedupea por display_label y puede
    colapsar sector_codes distintos con cobertura distinta en una sola
    sugerencia. Acá la frescura importa (decide si se bloquea a un cliente),
    no es cosmético como la lista de sugerencias."""
    view_name = load_location_catalog_settings().view_name
    query = text(
        f"SELECT cobertura_ventas FROM {view_name} WHERE sector_code = :sector_code"  # noqa: S608 — view_name es config del operador
    )
    try:
        with db.engine.connect() as connection:
            row = connection.execute(query, {"sector_code": sector_code}).first()
    except SQLAlchemyError:
        logger.exception("No se pudo leer cobertura_ventas para sector_code=%s", sector_code)
        return None
    return None if row is None else bool(row.cobertura_ventas)


def is_reachable() -> bool:
    """Chequeo liviano de conectividad al DWH (indicador de estado del wizard,
    ver app/forms/router.py) — un SELECT 1 puro, no depende de view_name ni de
    que la vista esté bien configurada, solo de la conexión a MySQL."""
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("mobilia_dwh no está respondiendo (chequeo de disponibilidad)")
        return False
    return True


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
