"""Detecta si un chat de WhatsApp visto por primera vez localmente ya tenía historial en Waha.

Separado de `whatsapp_bot.py` (límite de 500 líneas del repo) — mismo motivo
que `whatsapp_bot_conversation_store.py`/`whatsapp_bot_llm.py`. Usado por
`_process()` justo al crear el lead por primera vez (`ConversationStore.chat_exists`)
para decidir el `bot_enabled` inicial: auto-activación si el chat es
genuinamente nuevo (Tarea 5), apagado si ya había alguien hablando ahí
(cliente o asesor por WhatsApp Web) antes de que el bot existiera para ese
chat_id.
"""
from __future__ import annotations

from app.waha.client import WahaClient
from app.waha.inbound import InboundMessage

# Alcanza con 2: solo hace falta distinguir "el único mensaje que Waha
# conoce de este chat es el que acaba de disparar este webhook" de "hay al
# menos uno más" — no se necesita traer el historial completo acá (eso lo
# hace, si corresponde, `seed_history_from_waha` cuando un admin activa el
# chat a mano).
_NEW_CHAT_HISTORY_CHECK_LIMIT = 2


def is_chat_new_in_waha(inbound: InboundMessage, waha_client: WahaClient) -> bool:
    """True si, según Waha, este chat NO tenía mensajes antes del que acaba de llegar.

    Se llama una sola vez por chat, justo al crear el lead por primera vez
    (ver `_process` en whatsapp_bot.py) — nunca en mensajes subsiguientes de
    un chat ya conocido, ver `ConversationStore.chat_exists`. Compara por
    `id` de mensaje (mismo shape que devuelve `WahaClient.get_chat_messages`,
    ver su docstring) en vez de por timestamp: Waha ya incluye el mensaje
    entrante actual en su propio historial para cuando este webhook se
    procesa, así que "sin historial previo" es "lo único que aparece es este
    mismo id".

    Si la consulta a Waha falla (`None`) se falla cerrado: se trata como si
    hubiera historial previo (`bot_enabled` queda apagado) — más seguro no
    interrumpir una conversación existente (cliente o asesor ya hablando ahí)
    que arriesgar una auto-activación sin poder verificarlo de verdad.
    """
    messages = waha_client.get_chat_messages(
        inbound.chat_id, limit=_NEW_CHAT_HISTORY_CHECK_LIMIT, session=inbound.session
    )
    if messages is None:
        return False
    prior_messages = [m for m in messages if str(m.get("id")) != inbound.message_id]
    return len(prior_messages) == 0
