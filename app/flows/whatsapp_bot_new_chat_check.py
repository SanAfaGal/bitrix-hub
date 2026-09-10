"""Detecta si un chat de WhatsApp visto por primera vez localmente ya tenía una conversación real en Waha.

Separado de `whatsapp_bot.py` (límite de 500 líneas del repo) — mismo motivo
que `whatsapp_bot_conversation_store.py`/`whatsapp_bot_llm.py`. Usado por
`_process()` justo al crear el lead por primera vez (`ConversationStore.chat_exists`)
para decidir el `bot_enabled` inicial: auto-activación si el chat es
genuinamente nuevo o nadie de nuestro lado lo contestó nunca, apagado si ya
hay un asesor atendiéndolo a mano por WhatsApp Web (mensajes previos de
AMBOS lados) antes de que el bot existiera para ese chat_id.
"""
from __future__ import annotations

from app.waha.client import WahaClient
from app.waha.inbound import InboundMessage

# No alcanza con 2: además del mensaje que acaba de disparar el webhook y
# el placeholder de cifrado que casi siempre lo precede (ver docstring de
# `is_chat_new_in_waha`), hace falta margen para encontrar mensajes reales
# de AMBOS lados si los hay — no se necesita traer el historial completo
# acá (eso lo hace, si corresponde, `seed_history_from_waha` cuando un
# admin activa el chat a mano), solo una ventana razonable.
_NEW_CHAT_HISTORY_CHECK_LIMIT = 10


def is_chat_new_in_waha(inbound: InboundMessage, waha_client: WahaClient) -> bool:
    """True si, según Waha, este chat NO tenía una conversación real antes del mensaje que acaba de llegar.

    Se llama una sola vez por chat, justo al crear el lead por primera vez
    (ver `_process` en whatsapp_bot.py) — nunca en mensajes subsiguientes de
    un chat ya conocido, ver `ConversationStore.chat_exists`.

    "Conversación real ya existente" exige un mensaje anterior de CADA
    lado (`fromMe=True` y `fromMe=False`) — no alcanza con que solo el
    cliente haya escrito antes sin que nunca le hayan contestado (lead que
    se cayó, ningún asesor lo tocó todavía): ahí no hay nada humano que el
    bot vaya a interrumpir, así que se auto-activa igual. Si en cambio ya
    hay un asesor que le escribió a mano por WhatsApp Web (o el cliente le
    escribió y el asesor ya respondió), se asume que ese asesor sigue
    atendiendo el chat y se deja apagado para activación manual.

    Compara por `id` de mensaje (mismo shape que devuelve
    `WahaClient.get_chat_messages`, ver su docstring) en vez de por
    timestamp: Waha ya incluye el mensaje entrante actual en su propio
    historial para cuando este webhook se procesa.

    Si la consulta a Waha falla (`None`) se falla cerrado: se trata como si
    hubiera conversación previa (`bot_enabled` queda apagado) — más seguro
    no interrumpir una conversación existente que arriesgar una
    auto-activación sin poder verificarlo de verdad.

    Antes del mensaje de texto real, WhatsApp manda un evento
    `e2e_notification`/`encrypt` (placeholder de intercambio de claves) que
    Waha guarda como un mensaje más del chat, con `id` propio (distinto del
    mensaje real) y `body` vacío — `app.waha.inbound.parse_inbound_message`
    ya lo descarta al llegar por webhook, pero queda para siempre en el
    historial. Se descarta junto con el mensaje actual exigiendo `body` no
    vacío, no solo comparando por `id` — si no, contaría como mensaje real
    de un lado y podría disparar el "ambos lados escribieron" con solo un
    mensaje genuino.
    """
    messages = waha_client.get_chat_messages(
        inbound.chat_id, limit=_NEW_CHAT_HISTORY_CHECK_LIMIT, session=inbound.session
    )
    if messages is None:
        return False
    prior_messages = [
        m
        for m in messages
        if str(m.get("id")) != inbound.message_id and m.get("body")
    ]
    has_incoming = any(not m.get("fromMe") for m in prior_messages)
    has_outgoing = any(m.get("fromMe") for m in prior_messages)
    return not (has_incoming and has_outgoing)
