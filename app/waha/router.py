"""Endpoints HTTP de la integración con Waha (WhatsApp)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.crm.deps import get_crm_client
from app.crm.protocol import CrmClient
from app.flows.whatsapp_bot import load_bot_config
from app.flows.whatsapp_bot import process as process_whatsapp_bot
from app.llm.client import LlmClient
from app.llm.deps import get_llm_client
from app.waha.client import WahaClient
from app.waha.deps import get_waha_client
from app.waha.inbound import parse_inbound_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Waha"])


@router.post(
    "/webhook/waha-test",
    summary="Probar el envío de un mensaje de WhatsApp (scaffolding)",
)
def webhook_waha_test(
    chat_id: str = Query(description="Chat de WhatsApp en formato Waha.", examples=["573001112233@c.us"]),
    text: str = Query(default="Prueba desde bitrix-hub", description="Texto del mensaje a enviar."),
    session: str | None = Query(
        default=None,
        description="Sesión de Waha a usar (línea/número). Si se omite, usa WAHA_SESSION de .env.",
        examples=["default"],
    ),
    client: WahaClient = Depends(get_waha_client),
) -> dict[str, Any]:
    """Endpoint de scaffolding: valida que WahaClient puede enviar un mensaje.

    No cablea ningún flujo de negocio real todavía — se reemplaza por un
    endpoint por disparador de Bitrix cuando se implemente el primer flujo
    que use Waha (ver app/flows/README.md).
    """
    sent = client.send_text(chat_id, text, session=session)
    return {"ok": sent, "chat_id": chat_id, "session": session or client.session}


@router.post(
    "/webhook/waha-message",
    summary="Bot conversacional de WhatsApp (experimental)",
)
async def webhook_waha_message(
    request: Request,
    waha_client: WahaClient = Depends(get_waha_client),
) -> dict[str, Any]:
    """Recibe el webhook `message` de Waha y responde con el bot LLM.

    **Experimental** — apagado por defecto (`WHATSAPP_BOT_ENABLED=false`).
    Configurar en Waha (`WHATSAPP_HOOK_URL`/`WHATSAPP_HOOK_EVENTS` en `.env`,
    ver README) para que reenvíe acá los eventos `message` de una sesión.
    Ignora mensajes propios del bot (`fromMe`), con media, o ya procesados
    (dedup por `message_id`, Waha puede reintentar el webhook). La lógica de
    negocio (Waha + LLM + CRM) vive en `app/flows/whatsapp_bot.py` — los
    datos del inmueble que el cliente cuenta se guardan en el deal de
    consignación de Bitrix.
    """
    event = await request.json()
    inbound = parse_inbound_message(event)
    if inbound is None:
        return {"ok": True, "skipped": "not_applicable"}

    config = load_bot_config()
    if not config.enabled:
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_disabled"}

    try:
        llm_client: LlmClient = get_llm_client()
    except Exception:  # noqa: BLE001 — get_llm_client ya loguea/traduce el error real
        logger.error("Bot de WhatsApp: no se pudo construir el cliente LLM (falta configuración)")
        return {"ok": False, "chat_id": inbound.chat_id, "error": "llm_not_configured"}

    try:
        crm_client: CrmClient = get_crm_client()
    except Exception:  # noqa: BLE001 — get_crm_client ya loguea/traduce el error real
        logger.error("Bot de WhatsApp: no se pudo construir el cliente de CRM (falta configuración)")
        return {"ok": False, "chat_id": inbound.chat_id, "error": "crm_not_configured"}

    return process_whatsapp_bot(inbound, waha_client, llm_client, crm_client, config=config)
