"""Flujo: matrícula tecleada en vivo por el cliente (wizard del formulario de
Autorización de Corretaje) -> consulta en Xposure -> constancia en el CRM si hay deal.

Combina app.crm (opcional, para dejar constancia si ya hay deal) con
app.xposure (para la consulta externa) — por eso vive en app/flows/, no en
app/forms/, igual que app/flows/registry_duplicate_check.py. A diferencia de
`process_deal_event` (que lee la matrícula ya guardada en el deal), acá la
matrícula llega recién tecleada por el cliente, antes de que exista o de que
el deal la tenga guardada — por eso `crm_client`/`deal_id` son opcionales.
"""
from __future__ import annotations

from typing import Any, Callable

from app.crm.protocol import CrmClient
from app.flows.registry_duplicate_check import check_matricula_in_xposure
from app.xposure.client import XposureClient


def check_registration_number_live(
    registration_number: str,
    get_xposure_client: Callable[[], XposureClient],
    crm_client: CrmClient | None = None,
    deal_id: str | None = None,
) -> dict[str, Any]:
    """Consulta una matrícula ya validada (formato correcto) en Xposure y responde si bloquea.

    Si hay `deal_id` y `crm_client`, deja la misma constancia en el deal que
    `process_deal_event` (comentario + Duplicado/Sin duplicado, fijado si es
    duplicado) — así el asesor ve en Bitrix que el cliente fue bloqueado acá,
    aunque el deal todavía no tuviera la matrícula guardada.
    """
    xposure_client = get_xposure_client()
    is_duplicate, comment = check_matricula_in_xposure(registration_number, xposure_client)

    if crm_client is not None and deal_id is not None:
        comment_id = crm_client.add_comment(deal_id, comment)
        if is_duplicate and comment_id is not None:
            crm_client.pin_comment(comment_id, deal_id)
        crm_client.set_duplicado_status(deal_id, is_duplicate)

    message = (
        "Este inmueble ya está publicado en el MLS, así que no podemos continuar con la "
        "Autorización de Corretaje para este registro."
        if is_duplicate
        else ""
    )
    return {"duplicate": is_duplicate, "message": message}
