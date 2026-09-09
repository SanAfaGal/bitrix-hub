"""Bienvenida de primer contacto del bot de WhatsApp: texto fijo, sin pasar por el LLM.

Separado de `whatsapp_bot.py` (ya en el límite de 500 líneas del repo) para
no seguir inflándolo. Se ejecuta antes de que `process()` invoque al LLM: si
el chat no tiene historial todavía, se resuelve si Bitrix ya conoce al
cliente por su teléfono (`CrmClient.find_contact_by_phone`) y se envía la
plantilla correspondiente (`whatsapp_welcome_known`/`whatsapp_welcome_unknown`,
ver `app/message_templates/store.py`) tal cual, sin generarla con el LLM. Si
el cliente es conocido, además se le manda de una vez la explicación del
proceso (`whatsapp_bot_explanation.maybe_send_explanation`) — sin preguntar
antes si la quiere.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.crm.protocol import CrmClient
from app.flows.whatsapp_bot_explanation import maybe_send_explanation
from app.message_templates import store as templates_store
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot import ConversationStore

logger = logging.getLogger(__name__)


def maybe_send_first_contact_welcome(
    chat_id: str,
    session: str,
    waha_client: WahaClient,
    crm_client: CrmClient,
    store: "ConversationStore",
) -> bool:
    """Si el chat no tiene historial ni deal todavía, manda la bienvenida fija y la registra.

    Retorna True cuando este turno ya quedó resuelto con la bienvenida (el
    caller no debe invocar al LLM), False cuando el chat ya venía en curso
    (turno normal, sigue el flujo del LLM). El teléfono se resuelve acá
    mismo (import local para evitar el ciclo `whatsapp_bot` <-> este
    módulo) — así un chat en curso no paga ese costo de más.

    La freshness se decide con `store.has_assistant_turn` (¿el bot ya le
    contestó algo alguna vez a este chat?), NO con `store.get_history`
    no-vacío: mientras `bot_enabled=False`, `_process()` en whatsapp_bot.py
    ya guarda cada mensaje entrante localmente (para que el chat aparezca en
    /admin/prospects) — eso deja historial local con solo turnos `role=
    "user"` para un chat que, desde la perspectiva del bot, nunca fue
    contactado. Con el criterio viejo, el caso típico de go-live (cliente
    nuevo escribe con el bot apagado, se guarda su mensaje, un admin activa
    el chat) hacía que la bienvenida nunca se mandara.
    """
    if store.has_assistant_turn(chat_id) or store.get_deal_id(chat_id) is not None:
        return False

    from app.flows.whatsapp_bot import _resolve_phone  # noqa: PLC0415 — evita el ciclo de imports

    phone, _ = _resolve_phone(chat_id, waha_client, session)

    contact = crm_client.find_contact_by_phone(phone) if phone else None
    name = crm_client.get_contact_full_name(contact) if contact else None

    if name:
        text = templates_store.render_template("whatsapp_welcome_known", nombre=name)
    else:
        text = templates_store.render_template("whatsapp_welcome_unknown")

    sent = waha_client.send_text(chat_id, text, session=session)
    if sent:
        store.add_turn(chat_id, "assistant", text)
    else:
        logger.error("No se pudo enviar la bienvenida de primer contacto a %s", chat_id)

    if sent and name:
        # Bitrix ya conocía este teléfono (por eso `name` no es None) — se
        # guarda la identidad y se resuelve el deal ACÁ MISMO, en vez de
        # esperar a que el LLM la vuelva a confirmar en un turno futuro.
        # Sin esto, un cliente que ya tenía contacto/deal en Bitrix quedaba
        # igual atrapado en el flujo de "¿cuál es tu nombre y teléfono?" —
        # el bot literalmente acababa de saludarlo por su nombre y volvía a
        # pedírselo dos turnos después (visto en producción).
        if phone:
            store.set_confirmed_identity(chat_id, name, phone)
            from app.flows.whatsapp_bot import _create_deal_from_confirmed_identity  # noqa: PLC0415

            _create_deal_from_confirmed_identity(chat_id, crm_client, store)

        maybe_send_explanation(chat_id, session, waha_client, store)

    return True
