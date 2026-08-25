"""Reglas de negocio que solo involucran Waha (sin otras integraciones).

Acá van las funciones de flujo que reciben un evento del CRM y solo
necesitan enviar (o, a futuro, recibir) un mensaje de WhatsApp — análogo a
`MLS/app/deal_event.py`, pero para Waha puro.

Un flujo que combina Waha con otra integración (ej. Xposure o Mobilia) NO
va acá — va en `app/flows/`, ver `app/flows/README.md`.

Ejemplo de forma esperada, una vez que haya un flujo real:

    def notify_stage_change(
        deal_id: str,
        crm_client: CrmClient,
        waha_client: WahaClient,
    ) -> dict[str, Any]:
        deal = crm_client.get_deal(deal_id)
        ...
        waha_client.send_text(chat_id, texto)
        return {"ok": True, "deal_id": deal_id}
"""
from __future__ import annotations

# Placeholder: sin flujos Waha-solo reales todavía (scaffolding únicamente).

# El parseo del webhook entrante de Waha vive en `app/waha/inbound.py`. La
# lógica de negocio del bot conversacional (Waha + LLM, experimental) vive
# en `app/flows/whatsapp_bot.py` porque combina dos integraciones — ver
# `app/flows/README.md`. El endpoint es `POST /webhook/waha-message`
# (`app/waha/router.py`).
