"""Endpoints HTTP de la integración con Waha (WhatsApp)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.waha.client import WahaClient
from app.waha.deps import get_waha_client

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
