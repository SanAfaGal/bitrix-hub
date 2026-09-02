"""Cache en memoria del catálogo de ubicaciones — evita una consulta al DWH
por cada carga del formulario.

La vista se refresca por un ETL externo con poca frecuencia, así que un TTL
largo es aceptable. Si el refresh falla (DWH caído), se sigue sirviendo el
cache viejo en vez de pisarlo con una lista vacía — y se entra en un
cooldown antes de reintentar, mismo patrón que
`app/message_templates/store.py`, para no esperar el connect_timeout
completo en cada carga del formulario mientras la base está caída.
"""
from __future__ import annotations

import threading
import time

from app.location_catalog.client import LocationSuggestion, fetch_all_locations

CACHE_TTL_SECONDS = 6 * 60 * 60
REFRESH_COOLDOWN_SECONDS = 30

_lock = threading.Lock()
_cached_locations: list[LocationSuggestion] = []
_last_refreshed_at = 0.0
_unavailable_until = 0.0


def get_cached_locations() -> list[LocationSuggestion]:
    global _last_refreshed_at, _unavailable_until

    now = time.monotonic()
    with _lock:
        is_fresh = _cached_locations and (now - _last_refreshed_at) < CACHE_TTL_SECONDS
        is_in_cooldown = now < _unavailable_until
        if is_fresh or is_in_cooldown:
            return list(_cached_locations)

    fetched = fetch_all_locations()

    with _lock:
        if fetched:
            _cached_locations[:] = fetched
            _last_refreshed_at = now
        else:
            # Deja el cache viejo tal cual (aunque esté vencido) y evita
            # reintentar en cada request mientras el DWH sigue caído.
            _unavailable_until = now + REFRESH_COOLDOWN_SECONDS
        return list(_cached_locations)


def reset_location_cache() -> None:
    """Solo para tests: limpia el estado del cache entre casos."""
    global _last_refreshed_at, _unavailable_until
    with _lock:
        _cached_locations.clear()
        _last_refreshed_at = 0.0
        _unavailable_until = 0.0
