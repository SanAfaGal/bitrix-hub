"""Resolución de teléfono/identidad de un chat de WhatsApp — sin dependencia hacia
`whatsapp_bot.py`, a propósito: varios módulos "satélite" (`whatsapp_bot_welcome.py`,
`whatsapp_bot_history_seed.py`) necesitaban esto y terminaban importándolo de vuelta desde
`whatsapp_bot.py` con imports diferidos para evitar un ciclo. Vive acá, en un módulo de bajo
nivel del que todos importan hacia abajo, no entre sí.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.crm.protocol import CrmClient
from app.waha.client import WahaClient
from app.waha.phone import from_chat_id, lid_from_chat_id, to_chat_id

if TYPE_CHECKING:
    from app.flows.whatsapp_bot_conversation_store import ConversationStore


def resolve_phone(chat_id: str, waha_client: WahaClient, session: str) -> tuple[str | None, str | None]:
    """Resuelve el teléfono real de un chat de WhatsApp, devuelve `(phone, username)`.

    El identificador normal es el teléfono (`from_chat_id`). Si WhatsApp
    oculta el número del remitente, el chat llega como `@lid` en vez de
    `@c.us` — en ese caso primero se intenta resolver el teléfono real vía
    `WahaClient.resolve_lid_to_phone` (Waha lo sabe si ya compartió un
    grupo o chat directo con este número antes); si Waha tampoco lo sabe
    todavía, se devuelve el identificador `@lid` como `username`
    (`lid_from_chat_id`) y `phone=None`.
    """
    phone = from_chat_id(chat_id)
    username = None

    if phone is None:
        username = lid_from_chat_id(chat_id)
        if username is not None:
            resolved_chat_id = waha_client.resolve_lid_to_phone(username, session=session)
            if resolved_chat_id is not None:
                phone = from_chat_id(resolved_chat_id)

    return phone, username


def normalize_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    chat_id_form = to_chat_id(raw)
    return from_chat_id(chat_id_form) if chat_id_form else None


def create_deal_from_confirmed_identity(
    chat_id: str, crm_client: CrmClient, store: "ConversationStore"
) -> str | None:
    """Crea el contacto/deal de consignación en Bitrix si el store ya tiene nombre Y teléfono confirmados.

    No crea nada con solo uno de los dos — evita negociaciones a medio
    llenar visibles para un asesor. Se usa tanto para la primera creación
    como para el self-heal cuando un asesor borró el deal manualmente (la
    identidad ya confirmada sigue en el store, no hace falta volver a
    pedirla).
    """
    confirmed_name, confirmed_phone = store.get_confirmed_identity(chat_id)
    if confirmed_name is None or confirmed_phone is None:
        return None

    username = lid_from_chat_id(chat_id)
    contact_id = crm_client.find_or_create_property_seller_contact(confirmed_phone, username, confirmed_name)
    if contact_id is None:
        return None

    deal_id = crm_client.find_or_create_property_seller_deal(contact_id, source="whatsapp")
    if deal_id is not None:
        store.set_deal_id(chat_id, deal_id)
    return deal_id
