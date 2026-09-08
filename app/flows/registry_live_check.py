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

    Si se encuentra un duplicado, NO se toca el CRM todavía — el wizard le
    pregunta primero al cliente "¿es este tu inmueble?" (con el link acá
    devuelto) antes de bloquear, porque folios no son únicos entre oficinas
    distintas y un match sin código de oficina confirmado podría ser un
    inmueble ajeno. La constancia en Bitrix (comentario + Duplicado/Sin
    duplicado) la deja `confirm_registration_number_match()` una vez el cliente
    responde. Cuando no es duplicado no hay nada que confirmar, así que sí se
    deja constancia de inmediato, igual que antes.
    """
    xposure_client = get_xposure_client()
    is_duplicate, comment, url, exact_match = check_matricula_in_xposure(registration_number, xposure_client)

    if not is_duplicate and crm_client is not None and deal_id is not None:
        crm_client.add_comment(deal_id, comment)
        crm_client.set_duplicado_status(deal_id, False)

    message = (
        "Este inmueble ya está publicado en Xposure MLS (la plataforma donde las inmobiliarias "
        "comparten su inventario), así que no podemos continuar con la Autorización de "
        "Corretaje para este registro."
        if is_duplicate
        else ""
    )
    return {"duplicate": is_duplicate, "exact_match": exact_match, "message": message, "url": url}


def confirm_registration_number_match(
    registration_number: str,
    url: str | None,
    confirmed: bool,
    crm_client: CrmClient | None = None,
    deal_id: str | None = None,
) -> dict[str, Any]:
    """Deja constancia en el CRM de la respuesta del cliente a "¿es este tu inmueble?"

    Llamada por el wizard después de `check_registration_number_live` haber
    encontrado un duplicado y preguntado — acá sí se actualiza Bitrix, ahora
    que la persona ya confirmó o descartó el match.
    """
    if crm_client is not None and deal_id is not None:
        comment = (
            f"El cliente confirmó que el inmueble encontrado en Xposure es el suyo. Ver: {url}"
            if confirmed
            else (
                f'El cliente indicó que el inmueble encontrado en Xposure para la matrícula "{registration_number}" '
                f"NO es el suyo — probablemente escribió mal el código de oficina o el folio. Ver: {url}"
            )
        )
        comment_id = crm_client.add_comment(deal_id, comment)
        if confirmed and comment_id is not None:
            crm_client.pin_comment(comment_id, deal_id)
        crm_client.set_duplicado_status(deal_id, confirmed)

    return {"ok": True}
