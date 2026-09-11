"""Pregunta de cobertura de zona (Medellín / Oriente antioqueño), antes de la explicación.

Mismo shape que `whatsapp_bot_explanation.py`, al que precede en el flujo:

1. `maybe_ask_zone`: apenas se confirma la identidad del cliente (o al saludar a uno ya
   conocido en Bitrix, `whatsapp_bot_welcome.py`) se le pregunta si su inmueble está en
   Medellín o el Oriente antioqueño — el negocio solo gestiona este proceso ahí, un
   inmueble de otra zona lo atiende un asesor distinto.
2. `maybe_handle_zone_response`: interpreta la respuesta con los mismos regex de
   afirmación/negación que `maybe_handle_acceptance`. Si confirma, se sigue con
   `maybe_send_explanation`. Si niega, se manda el aviso de fuera de cobertura y se
   desactiva el bot para ese chat (`bot_enabled=False`, mismo mecanismo usado para
   pausarlo manualmente) — un asesor le hace seguimiento aparte. Una respuesta que no cae
   limpio en ninguno de los dos regex no se maneja acá: el caller le pasa el turno al LLM
   para que vuelva a preguntar.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.flows.whatsapp_bot_explanation import maybe_send_explanation
from app.flows.whatsapp_bot_llm import AFFIRMATION_RE as _AFFIRMATION_RE
from app.flows.whatsapp_bot_llm import NEGATION_RE as _NEGATION_RE
from app.message_templates import store as templates_store
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot_conversation_store import ConversationStore


def maybe_ask_zone(chat_id: str, session: str, waha_client: WahaClient, store: "ConversationStore") -> bool:
    """Manda la pregunta de cobertura de zona una sola vez.

    Retorna `True` cuando este turno ya quedó resuelto acá (el caller no debe invocar al
    LLM), `False` cuando la pregunta ya se había mandado antes.
    """
    if store.get_zone_asked(chat_id):
        return False

    text = templates_store.get_template("whatsapp_ask_zone")
    if waha_client.send_text(chat_id, text, session=session):
        store.add_turn(chat_id, "assistant", text)
        store.set_zone_asked(chat_id)
    return True


def maybe_handle_zone_response(
    chat_id: str,
    text: str,
    waha_client: WahaClient,
    session: str,
    store: "ConversationStore",
    created_at: float | None = None,
) -> bool:
    """Si ya se preguntó la zona y sigue sin resolver, interpreta un sí/no claro y actúa.

    Retorna `False` (y no hace nada) si la pregunta todavía no se mandó, si la zona ya
    quedó resuelta antes, o si `text` no es ni una afirmación ni una negación clara — en
    cualquiera de esos casos el caller sigue con el turno normal.
    """
    if not store.get_zone_asked(chat_id):
        return False

    if store.get_zone_in_coverage(chat_id) is not None:
        return False

    stripped = text.strip()

    if _AFFIRMATION_RE.match(stripped):
        store.add_turn(chat_id, "user", text, created_at)
        store.set_zone_in_coverage(chat_id, True)
        maybe_send_explanation(chat_id, session, waha_client, store)
        return True

    if _NEGATION_RE.match(stripped):
        store.add_turn(chat_id, "user", text, created_at)
        store.set_zone_in_coverage(chat_id, False)
        out_text = templates_store.get_template("whatsapp_zone_out_of_coverage")
        if waha_client.send_text(chat_id, out_text, session=session):
            store.add_turn(chat_id, "assistant", out_text)
        store.set_bot_enabled(chat_id, False, reason="zone_out_of_coverage")
        return True

    return False
