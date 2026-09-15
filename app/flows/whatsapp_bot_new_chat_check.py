"""Detecta si un chat de WhatsApp visto por primera vez localmente ya tenía una conversación real en Waha.

Separado de `whatsapp_bot.py` (límite de 500 líneas del repo) — mismo motivo
que `whatsapp_bot_conversation_store.py`/`whatsapp_bot_llm.py`. Usado por
`_process()` justo al crear el lead por primera vez (`ConversationStore.chat_exists`)
para decidir el `bot_enabled` inicial: auto-activación solo si el chat es
genuinamente nuevo (sin ningún mensaje real previo, de ningún lado),
apagado para activación manual si hay cualquier mensaje real previo —
del cliente, de un asesor a mano por WhatsApp Web, o de ambos — antes de
que el bot existiera para ese chat_id.
"""
from __future__ import annotations

from app.waha.client import WahaClient
from app.waha.inbound import InboundMessage

# Cada lado se consulta por separado (ver `is_chat_new_in_waha`), así que no
# hace falta una ventana grande por llamada: alcanza con encontrar UN
# mensaje real (no placeholder) de ese lado. 3 da margen para el placeholder
# de cifrado que casi siempre precede al mensaje real sin traer de más — no
# se necesita traer el historial completo acá (eso lo hace, si corresponde,
# `seed_history_from_waha` cuando un admin activa el chat a mano).
_NEW_CHAT_HISTORY_CHECK_LIMIT = 3


def is_chat_new_in_waha(inbound: InboundMessage, waha_client: WahaClient) -> bool:
    """True si, según Waha, este chat NO tenía una conversación real antes del mensaje que acaba de llegar.

    Se llama una sola vez por chat, justo al crear el lead por primera vez
    (ver `_process` en whatsapp_bot.py) — nunca en mensajes subsiguientes de
    un chat ya conocido, ver `ConversationStore.chat_exists`.

    "Conversación real ya existente" alcanza con un mensaje previo real de
    CUALQUIER lado (`fromMe=True` o `fromMe=False`) — incluido el caso de
    un lead que escribió y nadie le contestó todavía: aunque no haya un
    asesor atendiéndolo a mano, ya hay contexto real que el bot no debe
    arrancar ignorando (y que puede seguir llegando mientras el hub estuvo
    apagado, ver `whatsapp_bot_history_seed.seed_history_from_waha`, que sí
    se dispara para este mismo chat apenas se lo activa a mano). Se deja
    apagado para activación manual en ambos casos.

    Compara por `id` de mensaje (mismo shape que devuelve
    `WahaClient.get_chat_messages`, ver su docstring) en vez de por
    timestamp: Waha ya incluye el mensaje entrante actual en su propio
    historial para cuando este webhook se procesa.

    Si la consulta a Waha falla (`None`, cualquiera de las dos) se falla
    cerrado: se trata como si hubiera conversación previa (`bot_enabled`
    queda apagado) — más seguro no interrumpir una conversación existente
    que arriesgar una auto-activación sin poder verificarlo de verdad.

    Antes del mensaje de texto real, WhatsApp manda un evento
    `e2e_notification`/`encrypt` (placeholder de intercambio de claves) que
    Waha guarda como un mensaje más del chat, con `id` propio (distinto del
    mensaje real) y `body` vacío — `app.waha.inbound.parse_inbound_message`
    ya lo descarta al llegar por webhook, pero queda para siempre en el
    historial. Se descarta junto con el mensaje actual exigiendo `body` no
    vacío, no solo comparando por `id` — si no, contaría como mensaje real
    de un lado y podría disparar el "ambos lados escribieron" con solo un
    mensaje genuino.

    Se consulta cada lado por separado (`filter.fromMe` de Waha, ver
    `WahaClient.get_chat_messages`) en vez de traer los últimos N mensajes
    mezclados: si el cliente mandó varios mensajes seguidos justo antes de
    este chequeo, esos mensajes desplazarían fuera de una ventana mezclada
    al único mensaje del asesor humano, y el chat se trataría como
    genuinamente nuevo aunque no lo sea (bug real).
    """
    outgoing = waha_client.get_chat_messages(
        inbound.chat_id, limit=_NEW_CHAT_HISTORY_CHECK_LIMIT, from_me=True, session=inbound.session
    )
    incoming = waha_client.get_chat_messages(
        inbound.chat_id, limit=_NEW_CHAT_HISTORY_CHECK_LIMIT, from_me=False, session=inbound.session
    )
    if outgoing is None or incoming is None:
        return False

    def _has_real_prior_message(messages: list[dict]) -> bool:
        return any(str(m.get("id")) != inbound.message_id and m.get("body") for m in messages)

    return not (_has_real_prior_message(incoming) or _has_real_prior_message(outgoing))
