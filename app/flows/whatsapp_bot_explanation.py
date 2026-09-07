"""Explicación fija del proceso + pregunta de aceptación, entre la creación del deal y el link.

Separado de `whatsapp_bot.py` por el mismo motivo que `whatsapp_bot_welcome.py`
(límite de 500 líneas). Se ejecuta en dos puntos de `process()`:

1. `maybe_send_explanation`: apenas se crea el deal en este mismo turno
   (nombre y teléfono ya confirmados) — o apenas se saluda a un cliente ya
   conocido en Bitrix (`whatsapp_bot_welcome.py`) — se manda el texto de
   explicación, la nota de voz y la pregunta de aceptación de una sola vez,
   sin preguntar antes si la quiere: se asume que sí. Antes existía un paso
   intermedio ("¿Te gustaría que te explique?") que la persona tenía que
   confirmar; se sacó porque agregaba fricción y un estado
   (`explanation_offered`) que se prestaba a confusión si la respuesta no
   caía limpio en el regex de afirmación/negación.
2. `maybe_handle_acceptance`: una vez mandada la explicación, si la persona
   confirma con una afirmación clara, se reusa
   `process_welcome_and_authorization` para mandarle el link de la
   Autorización de Corretaje. Si no confirma claramente, el caller
   (`process()`) le pasa el turno al LLM para que responda la duda y
   vuelva a preguntar.

`maybe_handle_delayed_explanation_request` cubre el caso borde de que la
persona pida la explicación explícitamente (`LlmTurn.explanation_requested`)
antes de que se le haya podido mandar por el camino normal (ej. todavía no
se confirma su identidad) — mismo contenido que `maybe_send_explanation`,
sin el texto introductorio.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.crm.protocol import CrmClient
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.flows.whatsapp_bot_assets import process_explanation_voice_base64
from app.flows.whatsapp_bot_llm import AFFIRMATION_RE as _AFFIRMATION_RE
from app.message_templates import store as templates_store
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot import ConversationStore


def _send_voice_and_ask_acceptance(chat_id: str, session: str, waha_client: WahaClient, store: "ConversationStore") -> None:
    audio_base64 = process_explanation_voice_base64()
    if audio_base64 is not None:
        waha_client.send_voice(chat_id, audio_base64, session=session)
        store.add_turn(chat_id, "assistant", "[Nota de voz enviada: explicación del proceso de consignación]")

    ask_text = templates_store.get_template("whatsapp_ask_acceptance")
    waha_client.send_text(chat_id, ask_text, session=session)
    store.add_turn(chat_id, "assistant", ask_text)


def maybe_send_explanation(chat_id: str, session: str, waha_client: WahaClient, store: "ConversationStore") -> bool:
    """Manda texto + audio + pregunta de aceptación de una sola vez, sin preguntar antes.

    Retorna `True` cuando este turno ya quedó resuelto acá (el caller no debe
    invocar al LLM), `False` cuando la explicación ya se había mandado antes.
    """
    if store.get_explanation_sent(chat_id):
        return False

    process_text = templates_store.get_template("whatsapp_process_explanation")
    waha_client.send_text(chat_id, process_text, session=session)
    store.add_turn(chat_id, "assistant", process_text)

    _send_voice_and_ask_acceptance(chat_id, session, waha_client, store)

    store.set_explanation_sent(chat_id)
    return True


def maybe_handle_delayed_explanation_request(
    chat_id: str, requested: bool, waha_client: WahaClient, session: str, store: "ConversationStore"
) -> bool:
    """Si la persona pide la explicación explícitamente antes de que se le haya podido mandar
    por el camino normal (`maybe_send_explanation`), se la manda acá — mismo contenido, sin el
    texto introductorio. `requested` viene de la IA (`LlmTurn.explanation_requested`), no de un
    regex, ya que puede pedirse con cualquier redacción y en medio de otro tema.
    """
    if not requested:
        return False
    if store.get_explanation_sent(chat_id):
        return False

    # El mensaje de la persona que pidió esto ya se registró en `process()`
    # (este helper se llama después del turno normal del LLM) — acá solo
    # falta registrar lo que el bot manda de más.
    _send_voice_and_ask_acceptance(chat_id, session, waha_client, store)

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

    # Este turno se resuelve acá sin pasar por el LLM, así que hay que
    # registrar el mensaje de la persona a mano.
    store.add_turn(chat_id, "user", text)

    result = process_welcome_and_authorization(
        deal_id, crm_client, waha_client, public_base_url, link_secret, session=session
    )
    if result.get("ok"):
        store.set_authorization_link_sent(chat_id)
        store.add_turn(
            chat_id, "assistant", "[Se envió el enlace de la Autorización de Corretaje para completar y firmar]"
        )
    return bool(result.get("ok"))
