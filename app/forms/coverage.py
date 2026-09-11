"""Chequeo de cobertura por ubicación (paso del wizard, ver app/forms/router.py).

Decisión de negocio: si no se puede determinar la cobertura (DWH caído,
sector_code no reconocido), se deja pasar al cliente — no se bloquea por un
problema técnico nuestro. Solo bloquea cuando el dato real dice explícitamente
que no hay cobertura. Sin sector_code (no debería pasar: el frontend obliga a
elegir una sugerencia antes de llegar acá) sigue bloqueando, porque ahí no hay
nada que consultar."""
from __future__ import annotations

from dataclasses import dataclass

from app.location_catalog.client import get_sector_coverage


def is_location_covered(sector_code: str | None) -> bool:
    if not sector_code:
        return False
    covered = get_sector_coverage(sector_code)
    if covered is None:
        return True  # DWH caído o sector_code no reconocido: no bloqueamos por un problema nuestro
    return covered


@dataclass(frozen=True)
class CoverageResult:
    """Resultado del chequeo de cobertura, ya con la decisión de negocio tomada
    (bloquea o no) — el caller no vuelve a interpretar `covered`, solo actúa
    sobre `blocked`."""

    covered: bool
    blocked: bool
    used_exception: bool
    message: str | None


_PUBLIC_BLOCKED_MESSAGE = "En este momento no podemos continuar con el proceso para la ubicación indicada."
_INTERNAL_BLOCKED_MESSAGE = (
    "El inmueble se encuentra fuera de la zona de cobertura configurada. "
)


def check_coverage(sector_code: str | None, *, is_internal: bool, override: bool = False) -> CoverageResult:
    """Cobertura es obligatoria para todos, pero solo el flujo interno puede
    exceptuarla (`override=True`, tras ver la advertencia) — el público nunca
    puede, sin importar el valor de `override` que llegue.

    A diferencia de `is_location_covered` (que solo informa si hay cobertura),
    esto decide si bloquea — es lo que deben llamar los routers/flows en vez
    de reimplementar la regla "público bloquea siempre, interno puede
    exceptuar" cada vez.
    """
    covered = is_location_covered(sector_code)
    if covered:
        return CoverageResult(covered=True, blocked=False, used_exception=False, message=None)

    if not is_internal:
        return CoverageResult(covered=False, blocked=True, used_exception=False, message=_PUBLIC_BLOCKED_MESSAGE)

    if override:
        return CoverageResult(covered=False, blocked=False, used_exception=True, message=None)

    return CoverageResult(covered=False, blocked=True, used_exception=False, message=_INTERNAL_BLOCKED_MESSAGE)
