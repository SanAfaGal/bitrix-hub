"""Endpoints HTTP de la integración con Waha (WhatsApp)."""
from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.crm.deps import get_crm_client
from app.crm.protocol import CrmClient
from app.flows.whatsapp_bot import load_bot_config
from app.flows.whatsapp_bot import process as process_whatsapp_bot
from app.llm.client import LlmClient
from app.llm.deps import get_llm_client
from app.transcription.client import TranscriptionClient
from app.transcription.deps import get_transcription_client
from app.waha.client import WahaClient
from app.waha.deps import get_waha_client
from app.waha.inbound import parse_inbound_message
from app.waha.settings import load_waha_settings

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
    secret: str | None = Query(
        default=None, description="Debe coincidir con WHATSAPP_WEBHOOK_SECRET cuando esté configurado."
    ),
) -> dict[str, Any]:
    """Recibe el webhook `message` de Waha y responde con el bot LLM.

    **Experimental** — apagado por defecto (`WHATSAPP_BOT_ENABLED=false`).
    Configurar en Waha (`WHATSAPP_HOOK_URL`/`WHATSAPP_HOOK_EVENTS` en `.env`,
    ver README) para que reenvíe acá los eventos `message` de una sesión —
    agregar `?secret=...` a `WHATSAPP_HOOK_URL` si `WHATSAPP_WEBHOOK_SECRET`
    está configurado, si no cualquiera que descubra la URL puede disparar
    llamadas al LLM y creación de deals en Bitrix a nombre de un cliente
    inventado.
    Ignora mensajes propios del bot (`fromMe`) o ya procesados (dedup por
    `message_id`, Waha puede reintentar el webhook). Los mensajes de audio
    (notas de voz) se transcriben antes de pasar por el bot; media no
    soportada (imagen/video/documento) recibe una respuesta de fallback en
    vez de quedarse sin contestar. La lógica de negocio (Waha + LLM +
    CRM) vive en `app/flows/whatsapp_bot.py` — los datos del inmueble que el
    cliente cuenta se guardan en el deal de consignación de Bitrix.

    `process_whatsapp_bot` es síncrono y puede tardar varios segundos
    (transcripción de audio en CPU, `send_text_sequence` con pausas
    deliberadas) — se corre en un hilo aparte (`asyncio.to_thread`) para no
    bloquear el event loop de este endpoint mientras tanto.
    """
    expected_secret = load_waha_settings().webhook_secret
    if expected_secret is not None and not hmac.compare_digest(secret or "", expected_secret):
        raise HTTPException(status_code=401, detail="secret inválido o faltante")

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

    try:
        transcription_client: TranscriptionClient = get_transcription_client()
    except Exception:  # noqa: BLE001 — get_transcription_client ya loguea/traduce el error real
        logger.error("Bot de WhatsApp: no se pudo construir el cliente de transcripción (falta configuración)")
        return {"ok": False, "chat_id": inbound.chat_id, "error": "transcription_not_configured"}

    return await asyncio.to_thread(
        process_whatsapp_bot, inbound, waha_client, llm_client, crm_client, transcription_client, config=config
    )
