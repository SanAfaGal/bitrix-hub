"""Endpoints HTTP de la integración con Xposure: consulta de inmuebles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.xposure.client import XposureClient
from app.xposure.deps import get_xposure_client
from app.xposure.models import BulkRequest, PropertySearchResult

router = APIRouter(tags=["Xposure"])

_TAX_ROLL_EXAMPLE = "5322493"
_AREA_CODE_EXAMPLE = "001N"


def _search_property(
    client: XposureClient, tax_roll: str, tax_roll_area_code: str | None
) -> PropertySearchResult:
    try:
        if tax_roll_area_code is None:
            return client.search_property(tax_roll)
        return client.search_property(tax_roll, tax_roll_area_code=tax_roll_area_code)
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
    """Ejecuta una búsqueda por cada matrícula de la lista, en el mismo orden."""
    try:
        return [client.search_property(tax_roll) for tax_roll in payload.tax_rolls]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
