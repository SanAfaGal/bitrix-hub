"""Explicación fija del proceso + pregunta de aceptación, entre la creación del deal y el link.

Separado de `whatsapp_bot.py` por el mismo motivo que `whatsapp_bot_welcome.py`
(límite de 500 líneas). Se ejecuta en dos puntos de `process()`:

1. `maybe_send_explanation`: apenas se crea el deal en este mismo turno
   (nombre y teléfono ya confirmados), en vez de seguir con el LLM
   preguntando datos del inmueble, se manda texto + nota de voz (mismo
   archivo que `whatsapp_bot_welcome.process_explanation_voice_base64`) +
   pregunta de aceptación, sin pasar por el LLM.
2. `maybe_handle_acceptance`: en el siguiente turno, si la persona confirma
   con una afirmación clara, se reusa `process_welcome_and_authorization`
   para mandarle el link de la Autorización de Corretaje. Si no confirma
   claramente, el caller (`process()`) le pasa el turno al LLM para que
   responda la duda y vuelva a preguntar.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.crm.protocol import CrmClient
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.flows.whatsapp_bot_llm import AFFIRMATION_RE as _AFFIRMATION_RE
from app.flows.whatsapp_bot_welcome import process_explanation_voice_base64
from app.message_templates import store as templates_store
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot import ConversationStore


def maybe_send_explanation(chat_id: str, session: str, waha_client: WahaClient, store: "ConversationStore") -> bool:
    """Manda la explicación del proceso (texto + audio + pregunta) una sola vez por chat.

    Retorna `True` cuando este turno ya quedó resuelto acá (el caller no debe
    invocar al LLM), `False` cuando ya se había mandado antes.
    """
    if store.get_explanation_sent(chat_id):
        return False

    waha_client.send_text(chat_id, templates_store.get_template("whatsapp_process_explanation"), session=session)

    audio_base64 = process_explanation_voice_base64()
    if audio_base64 is not None:
        waha_client.send_voice(chat_id, audio_base64, session=session)

    waha_client.send_text(chat_id, templates_store.get_template("whatsapp_ask_acceptance"), session=session)

    store.set_explanation_sent(chat_id)
    return True


def maybe_handle_acceptance(
    chat_id: str,
    text: str,
    deal_id: str,
    crm_client: CrmClient,
    waha_client: WahaClient,
    session: str,
    public_base_url: str,
    link_secret: str,
    store: "ConversationStore",
) -> bool:
    """Si la persona ya vio la explicación y confirma, manda el link de Autorización.

    Retorna `False` (y no hace nada) si la explicación todavía no se mandó,
    si el link ya se mandó o firmó antes, o si `text` no es una afirmación
    clara — en cualquiera de esos casos el caller sigue con el turno normal.
    """
    if not store.get_explanation_sent(chat_id):
        return False

    deal = crm_client.get_deal(deal_id)
    if crm_client.get_authorization_status(deal) is not None:
        return False

    if not _AFFIRMATION_RE.match(text.strip()):
        return False

    process_welcome_and_authorization(
        deal_id, crm_client, waha_client, public_base_url, link_secret, session=session
    )
    return True
