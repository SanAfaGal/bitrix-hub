"""Chequeo de cobertura por ubicación (paso del wizard, ver app/forms/router.py).

Decisión de negocio: si no se puede determinar la cobertura (DWH caído,
sector_code no reconocido), se deja pasar al cliente — no se bloquea por un
problema técnico nuestro. Solo bloquea cuando el dato real dice explícitamente
que no hay cobertura. Sin sector_code (no debería pasar: el frontend obliga a
elegir una sugerencia antes de llegar acá) sigue bloqueando, porque ahí no hay
nada que consultar."""
from __future__ import annotations

from app.location_catalog.client import get_sector_coverage


def is_location_covered(sector_code: str | None) -> bool:
    if not sector_code:
        return False
    covered = get_sector_coverage(sector_code)
    if covered is None:
        return True  # DWH caído o sector_code no reconocido: no bloqueamos por un problema nuestro
    return covered
