"""Reglas de negocio que solo involucran Waha (sin otras integraciones).

Acá van las funciones de flujo que reciben un evento de Bitrix y solo
necesitan enviar (o, a futuro, recibir) un mensaje de WhatsApp — análogo a
`MLS/app/deal_event.py`, pero para Waha puro.

Un flujo que combina Waha con otra integración (ej. Xposure o Mobilia) NO
va acá — va en `app/flows/`, ver `app/flows/README.md`.

Ejemplo de forma esperada, una vez que haya un flujo real:

    def notify_stage_change(
        deal_id: str,
        bitrix_client: BitrixClient,
        waha_client: WahaClient,
    ) -> dict[str, Any]:
        deal = bitrix_client.get_deal(deal_id)
        ...
        waha_client.send_text(chat_id, texto)
        return {"ok": True, "deal_id": deal_id}
"""
from __future__ import annotations

# Placeholder: sin flujos reales todavía (scaffolding únicamente).

# Cuando exista el bot de WhatsApp (webhook entrante de Waha), su lógica de
# negocio (mensaje recibido -> crear/actualizar entidad en Bitrix) va en un
# módulo separado `app/waha/inbound.py`, con su propio endpoint en
# `app/main.py` (`/webhook/waha-message`). No implementado todavía.
