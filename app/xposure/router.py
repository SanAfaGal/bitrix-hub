"""Endpoints HTTP de la integración con Xposure: consulta de inmuebles."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.xposure.client import XposureClient, XposureSessionExpiredError
from app.xposure.deps import get_xposure_client, reset_xposure_client
from app.xposure.models import BulkRequest, PropertySearchResult

router = APIRouter(tags=["Xposure"])

_TAX_ROLL_EXAMPLE = "5322493"
_AREA_CODE_EXAMPLE = "001N"
_BULK_MAX_WORKERS = 5


def _search_property(
    client: XposureClient, tax_roll: str, tax_roll_area_code: str | None
) -> PropertySearchResult:
    try:
        if tax_roll_area_code is None:
            return client.search_property(tax_roll)
        return client.search_property(tax_roll, tax_roll_area_code=tax_roll_area_code)
    except XposureSessionExpiredError:
        # Sesión cacheada caducó (ver app.xposure.deps): descartarla y
        # reintentar una vez con un cliente recién autenticado.
        reset_xposure_client()
        fresh_client = get_xposure_client()
        try:
            if tax_roll_area_code is None:
                return fresh_client.search_property(tax_roll)
            return fresh_client.search_property(tax_roll, tax_roll_area_code=tax_roll_area_code)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/properties/{tax_roll}",
    response_model=PropertySearchResult,
    summary="Consultar un inmueble por matrícula (path)",
)
def get_property_path(
    tax_roll: str = Path(description="Número de matrícula (tax roll).", examples=[_TAX_ROLL_EXAMPLE]),
    tax_roll_area_code: str | None = Query(
        default=None, description="Código de área de la matrícula, si aplica.", examples=[_AREA_CODE_EXAMPLE]
    ),
    client: XposureClient = Depends(get_xposure_client),
) -> PropertySearchResult:
    """Busca el inmueble en Xposure y devuelve si existe, su MLS y el link al detalle."""
    return _search_property(client, tax_roll, tax_roll_area_code)


@router.post(
    "/properties/bulk",
    response_model=list[PropertySearchResult],
    summary="Consultar varias matrículas en una sola petición",
)
def get_properties_bulk(
    payload: BulkRequest,
    client: XposureClient = Depends(get_xposure_client),
) -> list[PropertySearchResult]:
    """Ejecuta una búsqueda por cada matrícula de la lista, en el mismo orden.

    Una matrícula que falle no descarta el resto del lote: queda como
    `exists=False` con el motivo del fallo en `reason`, y las demás se
    devuelven igual. Las búsquedas del lote corren en paralelo (mismo
    cliente/sesión, cada una es su propio round trip HTTP a Xposure) en vez
    de una tras otra — N matrículas ya no cuestan N tiempos de búsqueda
    seguidos.
    """

    def _one(tax_roll: str) -> PropertySearchResult:
        try:
            return _search_property(client, tax_roll, None)
        except HTTPException as exc:
            return PropertySearchResult(tax_roll=tax_roll, exists=False, reason=str(exc.detail))

    if not payload.tax_rolls:
        return []

    with ThreadPoolExecutor(max_workers=min(_BULK_MAX_WORKERS, len(payload.tax_rolls))) as executor:
        return list(executor.map(_one, payload.tax_rolls))
