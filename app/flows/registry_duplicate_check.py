"""Flujo: matrícula de un deal -> consulta en Xposure -> comentario/campo en el CRM.

Ejemplo del patrón de flujo encadenado descrito en app/flows/README.md:
combina app.crm (para leer/actualizar el deal) con app.xposure (para la
consulta externa). No importa nada de app.waha ni de otras integraciones.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from app.crm.protocol import CrmClient
from app.xposure.client import XposureClient

logger = logging.getLogger(__name__)

# [Código de Oficina (ORIP)]-[Número de Folio], ej. 50C-1945945 o 001-123456.
MATRICULA_PATTERN = re.compile(r"^\d{2,3}[A-Za-z]?-\d{4,10}$")


def process_deal_event(
    deal_id: str,
    crm_client: CrmClient,
    get_xposure_client: Callable[[], XposureClient],
) -> dict[str, Any]:
    """Lee la matrícula del deal, la consulta en Xposure y actualiza el CRM con el resultado."""
    deal = crm_client.get_deal(deal_id)
    matricula = crm_client.get_matricula(deal)

    if not matricula:
        logger.warning("Deal %s sin matrícula registrada", deal_id)
        crm_client.add_comment(
            deal_id, "Este negocio no tiene matrícula registrada, así que no se pudo validar en la MLS."
        )
        # No se tocó el campo Duplicado/Sin duplicado: no se pudo validar nada,
        # así que no hay resultado real que reflejar ahí (ver comentario).
        return {"ok": True, "deal_id": deal_id, "matricula": None}

    matricula = matricula.strip()
    if not MATRICULA_PATTERN.match(matricula):
        logger.warning("Deal %s matrícula con formato inválido: %s", deal_id, matricula)
        crm_client.add_comment(
            deal_id,
            f'La matrícula inmobiliaria "{matricula}" no tiene el formato requerido '
            "([Código de Oficina]-[Número de Folio], ej. 50C-1945945). No se pudo validar en la MLS.",
        )
        # Igual que sin matrícula: no se pudo validar nada, no se toca Duplicado/Sin duplicado.
        return {"ok": True, "deal_id": deal_id, "matricula": matricula}

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
    else:
        comentario = f"No se encontró el inmueble en Xposure para la matrícula {matricula}."

    comment_id = crm_client.add_comment(deal_id, comentario)
    if es_duplicado and comment_id is not None:
        crm_client.pin_comment(comment_id, deal_id)

    crm_client.set_duplicado_status(deal_id, es_duplicado)

    return {"ok": True, "deal_id": deal_id, "matricula": matricula}
