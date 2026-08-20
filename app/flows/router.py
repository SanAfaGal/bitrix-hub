"""Endpoints HTTP para webhooks de Bitrix que disparan flujos multi-integración."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request

from app.bitrix.deps import get_bitrix_client
from app.flows.deal_duplicado import process_deal_event
from app.flows.notify_contact import process_notify_contact
from app.flows.settings import load_public_base_url
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.waha.deps import get_waha_client
from app.xposure.deps import get_xposure_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bitrix Webhooks"])

_DEAL_ID_ALIAS_DATA_FIELDS = "data[FIELDS][ID]"
_DEAL_ID_ALIAS_DOCUMENT_ID_2 = "document_id[2]"


async def _resolve_deal_id(
    request: Request,
    deal_id_data_fields: str | None,
    document_id_2: str | None,
    deal_id_simple: str | None,
) -> str | None:
    """Bitrix manda el ID del deal en distintas formas según el tipo de automatización.

    Compartido por todos los webhooks disparados por deal — probamos las
    variantes conocidas en orden.
    """
    form = await request.form()

    deal_id = (
        deal_id_data_fields
        or document_id_2
        or form.get("document_id")
        or deal_id_simple
        or request.query_params.get("id")
    )

    if isinstance(deal_id, str) and deal_id.startswith("DEAL_"):
        deal_id = deal_id.replace("DEAL_", "")

    return str(deal_id) if deal_id else None


@router.post(
    "/webhook/deal-event",
    summary="Evento de deal de Bitrix -> consulta Xposure -> comentario/campo Duplicado",
)
async def webhook_deal_event(
    request: Request,
    deal_id_data_fields: str | None = Form(
        default=None,
        alias=_DEAL_ID_ALIAS_DATA_FIELDS,
        description="Así llega el ID del deal en el automation estándar de Bitrix (crm.deal.add / .update).",
        examples=["42"],
    ),
    document_id_2: str | None = Form(
        default=None,
        alias=_DEAL_ID_ALIAS_DOCUMENT_ID_2,
        description="Alternativa: así llega en algunos triggers de flujo de trabajo (business process) de Bitrix.",
    ),
    deal_id_simple: str | None = Form(
        default=None,
        alias="ID",
        description="Alternativa simple, útil para pruebas manuales con curl.",
        examples=["42"],
    ),
) -> dict[str, Any]:
    """Recibe un evento de deal de Bitrix y delega el procesamiento a app.flows.deal_duplicado.

    Lee la matrícula del deal (campo `UF_CRM_1773860489786`); si está
    presente, consulta Xposure y deja el resultado como comentario en el
    timeline (fijado solo si es duplicado) + actualiza el campo
    Duplicado/Sin duplicado (`UF_CRM_1773861337167`) del deal.
    """
    try:
        deal_id = await _resolve_deal_id(request, deal_id_data_fields, document_id_2, deal_id_simple)

        if not deal_id:
            logger.error("Evento de deal sin ID")
            return {"ok": False, "error": "Falta ID"}

        logger.info("Evento de deal recibido: %s", deal_id)

        bitrix_client = get_bitrix_client()
        return process_deal_event(deal_id, bitrix_client, get_xposure_client)
    except HTTPException as exc:
        logger.exception("Error procesando evento de deal")
        return {"ok": False, "error": str(exc.detail)}
    except Exception as exc:
        logger.exception("Error procesando evento de deal")
        return {"ok": False, "error": str(exc)}


@router.post(
    "/webhook/deal-notify-test",
    summary="Probar: deal de Bitrix -> contacto -> teléfono -> WhatsApp",
)
async def webhook_deal_notify_test(
    request: Request,
    deal_id_data_fields: str | None = Form(
        default=None,
        alias=_DEAL_ID_ALIAS_DATA_FIELDS,
        description="Así llega el ID del deal en el automation estándar de Bitrix (crm.deal.add / .update).",
        examples=["42"],
    ),
    document_id_2: str | None = Form(
        default=None,
        alias=_DEAL_ID_ALIAS_DOCUMENT_ID_2,
        description="Alternativa: así llega en algunos triggers de flujo de trabajo (business process) de Bitrix.",
    ),
    deal_id_simple: str | None = Form(
        default=None,
        alias="ID",
        description="Alternativa simple, útil para pruebas manuales con curl.",
        examples=["42"],
    ),
    text: str = Form(default="Prueba desde bitrix-hub", description="Texto del mensaje a enviar."),
    session: str | None = Form(
        default=None,
        description="Sesión de Waha a usar. Si se omite, usa WAHA_SESSION de .env.",
        examples=["default"],
    ),
) -> dict[str, Any]:
    """Endpoint de prueba: igual patrón que /webhook/deal-event, pero para Waha.

    Lee el deal, toma su `CONTACT_ID`, obtiene el contacto y su teléfono
    (`app.waha.phone.extract_phone_from_contact` + `to_chat_id`), y le
    manda `text` por WhatsApp. Todavía no es un disparador real de
    Bitrix — sirve para validar el flujo Bitrix -> contacto -> Waha antes
    de cablearlo a un evento real (ver app/flows/README.md). Acepta el
    mismo ID del deal que manda Bitrix, en las mismas variantes que
    `/webhook/deal-event`.
    """
    deal_id = await _resolve_deal_id(request, deal_id_data_fields, document_id_2, deal_id_simple)

    if not deal_id:
        logger.error("Evento de deal-notify-test sin ID")
        return {"ok": False, "error": "Falta ID"}

    bitrix_client = get_bitrix_client()
    try:
        waha_client = get_waha_client()
    except HTTPException as exc:
        logger.error("Evento de deal-notify-test %s no se pudo procesar: %s", deal_id, exc.detail)
        return {"ok": False, "error": str(exc.detail)}

    return process_notify_contact(deal_id, text, bitrix_client, waha_client, session=session)


@router.post(
    "/webhook/deal-stage-broker-auth",
    summary="Cambio de etapa de deal de Bitrix -> WhatsApp de bienvenida + enlace de Autorización de Corretaje",
)
async def webhook_deal_stage_broker_auth(
    request: Request,
    deal_id_data_fields: str | None = Form(
        default=None,
        alias=_DEAL_ID_ALIAS_DATA_FIELDS,
        description="Así llega el ID del deal en el automation estándar de Bitrix (crm.deal.add / .update).",
        examples=["42"],
    ),
    document_id_2: str | None = Form(
        default=None,
        alias=_DEAL_ID_ALIAS_DOCUMENT_ID_2,
        description="Alternativa: así llega en algunos triggers de flujo de trabajo (business process) de Bitrix.",
    ),
    deal_id_simple: str | None = Form(
        default=None,
        alias="ID",
        description="Alternativa simple, útil para pruebas manuales con curl.",
        examples=["42"],
    ),
    session: str | None = Form(
        default=None,
        description="Sesión de Waha a usar. Si se omite, usa WAHA_SESSION de .env.",
        examples=["default"],
    ),
) -> dict[str, Any]:
    """Recibe el evento de cambio de etapa y le manda al contacto del deal, por WhatsApp:

    1. Un mensaje de bienvenida.
    2. Tras una pausa aleatoria (simula comportamiento humano), el enlace al
       formulario público de Autorización de Corretaje, con el `deal_id`
       incluido para poder amarrar la firma al deal después.

    Apuntar acá la regla de automatización de Bitrix de la etapa que
    dispara este flujo.
    """
    deal_id = await _resolve_deal_id(request, deal_id_data_fields, document_id_2, deal_id_simple)

    if not deal_id:
        logger.error("Evento de deal-stage-broker-auth sin ID")
        return {"ok": False, "error": "Falta ID"}

    bitrix_client = get_bitrix_client()
    try:
        waha_client = get_waha_client()
        public_base_url = load_public_base_url()
    except (HTTPException, RuntimeError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.error("Evento de deal-stage-broker-auth %s no se pudo procesar: %s", deal_id, detail)
        return {"ok": False, "error": str(detail)}

    return await asyncio.to_thread(
        process_welcome_and_authorization, deal_id, bitrix_client, waha_client, public_base_url, session=session
    )
