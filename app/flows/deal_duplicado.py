"""Flujo: matrícula de un deal -> consulta en Xposure -> comentario/campo en Bitrix.

Ejemplo del patrón de flujo encadenado descrito en app/flows/README.md:
combina app.bitrix (para leer/actualizar el deal) con app.xposure (para la
consulta externa). No importa nada de app.waha ni de otras integraciones.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.bitrix.client import CRM_ENTITY_TYPE_DEAL, BitrixClient
from app.xposure.client import XposureClient

logger = logging.getLogger(__name__)

FIELD_MATRICULA = "UF_CRM_1773860489786"
FIELD_DUPLICADO = "UF_CRM_1773861337167"
VALUE_SIN_DUPLICADO = 89296
VALUE_DUPLICADO = 89298


def _comment(bitrix_client: BitrixClient, deal_id: str, comentario: str, *, pin: bool) -> None:
    """Agrega un comentario al deal. Solo lo fija en el timeline si `pin` es True.

    Se fija únicamente cuando el inmueble se encontró y es duplicado — el
    caso que de verdad necesita llamar la atención en el timeline. Los
    demás casos (sin matrícula, no encontrado) quedan como comentario
    normal, sin ocupar uno de los 3 espacios fijados del deal.
    """
    comment_id = bitrix_client.add_comment(deal_id, "deal", comentario)
    if pin and comment_id is not None:
        bitrix_client.pin_comment(comment_id, CRM_ENTITY_TYPE_DEAL, deal_id)


def process_deal_event(
    deal_id: str,
    bitrix_client: BitrixClient,
    get_xposure_client: Callable[[], XposureClient],
) -> dict[str, Any]:
    """Lee la matrícula del deal, la consulta en Xposure y actualiza Bitrix con el resultado."""
    deal = bitrix_client.get_deal(deal_id)
    matricula = deal.get(FIELD_MATRICULA)

    if not matricula:
        logger.warning("Deal %s sin campo %s", deal_id, FIELD_MATRICULA)
        _comment(
            bitrix_client, deal_id,
            "Este negocio no tiene matrícula registrada, así que no se pudo validar en Xposure.",
            pin=False,
        )
        bitrix_client.update_deal(deal_id, {FIELD_DUPLICADO: VALUE_SIN_DUPLICADO})
        return {"ok": True, "deal_id": deal_id, "matricula": None}

    logger.info("Deal %s matrícula: %s", deal_id, matricula)

    xposure_client = get_xposure_client()
    resultado = xposure_client.search_property(matricula)
    logger.info(
        "Consulta Xposure para deal %s: exists=%s mls=%s url=%s",
        deal_id, resultado.exists, resultado.mls, resultado.url,
    )

    es_duplicado = resultado.exists and bool(resultado.mls)
    if es_duplicado:
        comentario = f"Inmueble encontrado en Xposure. MLS: {resultado.mls}. Ver: {resultado.url}"
        valor_duplicado = VALUE_DUPLICADO
    else:
        comentario = f"No se encontró el inmueble en Xposure para la matrícula {matricula}."
        valor_duplicado = VALUE_SIN_DUPLICADO

    _comment(bitrix_client, deal_id, comentario, pin=es_duplicado)
    bitrix_client.update_deal(deal_id, {FIELD_DUPLICADO: valor_duplicado})

    return {"ok": True, "deal_id": deal_id, "matricula": matricula}
