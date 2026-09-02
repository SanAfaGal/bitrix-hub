"""Explicación fija del proceso + pregunta de aceptación, entre la creación del deal y el link.

Separado de `whatsapp_bot.py` por el mismo motivo que `whatsapp_bot_welcome.py`
(límite de 500 líneas). Se ejecuta en tres puntos de `process()`:

1. `maybe_send_explanation`: apenas se crea el deal en este mismo turno
   (nombre y teléfono ya confirmados), en vez de seguir con el LLM
   preguntando datos del inmueble, se manda texto + pregunta de si quiere
   la explicación (audio), sin pasar por el LLM ni mandar el audio todavía
   — el mismo gate lo usa `whatsapp_bot_welcome.py` para el cliente ya
   conocido en Bitrix.
2. `maybe_handle_explanation_response`: en el siguiente turno, si la
   persona confirma con una afirmación clara, recién ahí se manda la nota
   de voz (mismo archivo que
   `whatsapp_bot_welcome.process_explanation_voice_base64`) + la pregunta
   de aceptación. Si declina claramente, se marca y el bot no vuelve a
   ofrecerla ni avanza por su cuenta — ver `maybe_handle_acceptance`.
3. `maybe_handle_acceptance`: una vez mandada la explicación, si la persona
   confirma con una afirmación clara, se reusa
   `process_welcome_and_authorization` para mandarle el link de la
   Autorización de Corretaje. Si no confirma claramente, el caller
   (`process()`) le pasa el turno al LLM para que responda la duda y
   vuelva a preguntar.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.crm.protocol import CrmClient
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.flows.whatsapp_bot_llm import AFFIRMATION_RE as _AFFIRMATION_RE
from app.flows.whatsapp_bot_llm import NEGATION_RE as _NEGATION_RE
from app.flows.whatsapp_bot_welcome import process_explanation_voice_base64
from app.message_templates import store as templates_store
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot import ConversationStore


def maybe_send_explanation(chat_id: str, session: str, waha_client: WahaClient, store: "ConversationStore") -> bool:
    """Manda el texto de explicación + la pregunta de si quiere el audio, una sola vez por chat.

    Retorna `True` cuando este turno ya quedó resuelto acá (el caller no debe
    invocar al LLM), `False` cuando ya se había ofrecido antes.
    """
    if store.get_explanation_offered(chat_id):
        return False

    waha_client.send_text(chat_id, templates_store.get_template("whatsapp_process_explanation"), session=session)
    waha_client.send_text(chat_id, templates_store.get_template("whatsapp_offer_explanation"), session=session)

    store.set_explanation_offered(chat_id)
    return True


def maybe_handle_explanation_response(
    chat_id: str, text: str, waha_client: WahaClient, session: str, store: "ConversationStore"
) -> bool:
    """Si ya se ofreció el audio explicativo, maneja la respuesta de la persona a esa pregunta.

    Afirmación clara -> manda el audio + la pregunta de aceptación, marca
    `explanation_sent`. Negación clara -> responde con un mensaje breve, sin
    marcar nada ni avanzar por su cuenta al siguiente paso (si la persona lo
    pide más adelante, `maybe_handle_delayed_explanation_request` lo cubre).
    Cualquier otra cosa -> retorna `False`, el caller le pasa el turno al
    LLM (con la nota de "awaiting explicación") para que repita la pregunta.
    """
    if not store.get_explanation_offered(chat_id):
        return False
    if store.get_explanation_sent(chat_id):
        return False

    stripped = text.strip()

    if _AFFIRMATION_RE.match(stripped):
        audio_base64 = process_explanation_voice_base64()
        if audio_base64 is not None:
            waha_client.send_voice(chat_id, audio_base64, session=session)
        waha_client.send_text(chat_id, templates_store.get_template("whatsapp_ask_acceptance"), session=session)
        store.set_explanation_sent(chat_id)
        return True

    if _NEGATION_RE.match(stripped):
        waha_client.send_text(
            chat_id, templates_store.get_template("whatsapp_explanation_declined_ack"), session=session
        )
        return True

    return False


def maybe_handle_delayed_explanation_request(
    chat_id: str, requested: bool, waha_client: WahaClient, session: str, store: "ConversationStore"
) -> bool:
    """Si la persona pide el audio explícitamente en cualquier turno posterior a que se le
    ofreciera (haya respondido que no, o simplemente no haya respondido la oferta), se lo manda.

    Distinto de `maybe_handle_explanation_response`: ese resuelve la respuesta inmediata a la
    pregunta de oferta (sí/no); esto cubre que la persona lo pida más adelante, en cualquier
    turno posterior — por eso `requested` viene de la IA (`LlmTurn.explanation_requested`), no
    de un regex, ya que puede pedirse con cualquier redacción y en medio de otro tema.
    """
    if not requested:
        return False
    if not store.get_explanation_offered(chat_id) or store.get_explanation_sent(chat_id):
        return False

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

    "Ya se mandó" se decide con `store.get_authorization_link_sent` (local),
    no con `crm_client.get_authorization_status(deal) is None` — ese campo
    de Bitrix puede traer un valor por defecto no nulo desde que se crea el
    deal (`"pendiente_envio"`), así que "no es None" no significa "ya lo
    mandamos" (bug visto en producción: el gate nunca se abría y el bot
    quedaba prometiendo el link sin mandarlo). Como respaldo, también se
    bloquea si Bitrix ya muestra `"pendiente_firma"`/`"firmada"` — estados
    que sí escribe este mismo flujo (`set_authorization_status`), a
    diferencia del default ambiguo — para cubrir un deal cuyo tracking local
    se perdiera (ej. reset de la base) pero Bitrix ya sepa que se mandó.
    """
    if not store.get_explanation_sent(chat_id):
        return False

    if store.get_authorization_link_sent(chat_id):
        return False

    deal = crm_client.get_deal(deal_id)
    if crm_client.get_authorization_status(deal) in ("pendiente_firma", "firmada"):
        return False

    if not _AFFIRMATION_RE.match(text.strip()):
        return False

    result = process_welcome_and_authorization(
        deal_id, crm_client, waha_client, public_base_url, link_secret, session=session
    )
    if result.get("ok"):
        store.set_authorization_link_sent(chat_id)
    return bool(result.get("ok"))
