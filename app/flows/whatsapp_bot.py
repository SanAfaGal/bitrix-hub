"""Bot conversacional de WhatsApp — Waha (entrante) + LLM (app/llm/, cualquier proveedor compatible con OpenAI) + CRM.

**Experimental.** Combina tres integraciones (Waha + LLM + CRM), por eso
vive acá y no en `app/waha/` — ver `app/flows/README.md`. Apagado por
defecto (`WHATSAPP_BOT_ENABLED=false`); mientras esté apagado, el endpoint
sigue existiendo pero no llama al LLM ni responde.

Los datos del inmueble que el cliente cuenta (tipo, dirección, sector/zona/
ciudad, precio esperado, matrícula) se guardan directo en el deal de
consignación en Bitrix (`app.crm.protocol.PropertyListing`) — esa es la
fuente de verdad. El historial de turnos y el `deal_id` por chat
(`ConversationStore`) se persisten en SQLite (`whatsapp_bot_store.py`) y
sobreviven a un restart/deploy — solo el dedup de mensajes reintentados
por Waha queda en memoria del proceso (un TTL corto, sin problema si se
pierde).

Si un asesor pausa el bot para un deal puntual (checkbox en Bitrix,
`fields.FIELD_BOT_ACTIVE`), o el bot mismo lo pausa al detectar que la
persona pidió hablar con un humano, el webhook deja de responder para ese
chat hasta que el campo se reactive manualmente.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from app.crm.protocol import CrmClient, PropertyListing
from app.flows import whatsapp_bot_store as store_db
from app.forms.models import PROPERTY_TYPES
from app.llm.client import LlmClient
from app.waha.client import WahaClient
from app.waha.inbound import InboundMessage
from app.waha.phone import from_chat_id, lid_from_chat_id

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "Usted es el asistente virtual de Alberto Álvarez, una inmobiliaria, y "
    "atiende por WhatsApp a personas interesadas en vender su apartamento. "
    "Trate siempre de usted, nunca de tú ni de vos — mantenga un tono "
    "formal, profesional y amable en todo momento.\n\n"
    "Su objetivo es entender, poco a poco y sin interrogar de golpe, los "
    "datos básicos del inmueble que la persona quiere vender: tipo de "
    "inmueble, dirección, sector/zona/ciudad, precio de venta esperado y, "
    "si la tiene a la mano, la matrícula inmobiliaria — y ofrecerle "
    "agendar el contacto con un asesor humano para continuar el proceso. "
    "Usted no cierra negocios ni reemplaza al asesor.\n\n"
    "No dé cifras de avalúo ni valorización bajo ninguna circunstancia — "
    "eso lo define un asesor tras conocer el inmueble; el precio de venta "
    "esperado que usted recolecta es el que la persona misma menciona, no "
    "uno que usted sugiera. No dé asesoría legal, tributaria ni de "
    "trámites específicos; si le preguntan, indique que un asesor lo "
    "puede orientar en eso. No invente información sobre inmuebles, "
    "disponibilidad ni la empresa.\n\n"
    "Si la persona pide hablar con alguien, si su solicitud se sale de lo "
    "anterior, o si usted no tiene certeza de la respuesta, dígale con "
    "amabilidad que la va a conectar con un asesor.\n\n"
    "Responda en español, en mensajes breves y claros, como una "
    "conversación real de WhatsApp — sin markdown ni emojis."
)

_OUTPUT_FORMAT_INSTRUCTIONS = (
    "\n\nFormato de salida (obligatorio, sin excepción): responda ÚNICAMENTE "
    "con un objeto JSON válido, sin texto antes ni después, con esta forma "
    'exacta:\n{"reply": "<el mensaje que se le manda a la persona por '
    'WhatsApp>", "fields": {"property_type": <uno de ' + repr(list(PROPERTY_TYPES)) + " o null>, "
    '"address": <string o null>, "sector_zone_city": <string o null>, '
    '"expected_sale_price": <número entero o null>, "registration_number": '
    '<string o null>}, "handoff_requested": <true o false>}\n'
    'En "fields" solo van los datos que la persona haya mencionado o '
    'confirmado en ESTE turno — todo lo demás va en null, aunque ya lo '
    "sepamos de antes. No repita en \"fields\" un dato que ya aparece en la "
    'lista de "Datos que ya tenemos" salvo que la persona lo esté '
    "corrigiendo.\n"
    '"handoff_requested" es true únicamente cuando "reply" es el mensaje en '
    "el que usted le avisa a la persona que la va a conectar con un asesor "
    '(según las condiciones ya indicadas) — en cualquier otro caso, false.'
)


def _known_fields_block(listing: PropertyListing) -> str:
    def fmt(value: Any) -> str:
        return str(value) if value not in (None, "") else "(vacío)"

    return (
        "Datos que ya tenemos del inmueble (no vuelva a preguntar por lo "
        "que ya está lleno, solo confírmelo si la persona lo corrige):\n"
        f"- Tipo de inmueble: {fmt(listing.property_type)}\n"
        f"- Dirección: {fmt(listing.address)}\n"
        f"- Sector/zona/ciudad: {fmt(listing.sector_zone_city)}\n"
        f"- Precio de venta esperado: {fmt(listing.expected_sale_price)}\n"
        f"- Matrícula inmobiliaria: {fmt(listing.registration_number)}"
    )


def _build_system_prompt(base_prompt: str, listing: PropertyListing) -> str:
    return f"{base_prompt}\n\n{_known_fields_block(listing)}{_OUTPUT_FORMAT_INSTRUCTIONS}"


def _as_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_property_listing(data: dict[str, Any]) -> PropertyListing:
    property_type = data.get("property_type")
    if property_type not in PROPERTY_TYPES:
        property_type = None

    expected_sale_price = data.get("expected_sale_price")
    try:
        expected_sale_price = int(expected_sale_price) if expected_sale_price not in (None, "") else None
    except (TypeError, ValueError):
        expected_sale_price = None

    return PropertyListing(
        property_type=property_type,
        address=_as_text(data.get("address")),
        sector_zone_city=_as_text(data.get("sector_zone_city")),
        expected_sale_price=expected_sale_price,
        registration_number=_as_text(data.get("registration_number")),
    )


def _parse_llm_output(raw: str) -> tuple[str, PropertyListing, bool]:
    """Parsea la salida del LLM (JSON `{"reply": ..., "fields": ..., "handoff_requested": ...}`).

    Si el LLM no devolvió JSON válido (algún proveedor puede ignorar la
    instrucción), se trata todo el texto como la respuesta a mandar, no se
    actualiza ningún campo y no se pide handoff — nunca se rompe la
    conversación por esto.
    """
    data: Any = None
    try:
        data = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
            except ValueError:
                data = None

    if not isinstance(data, dict):
        return raw.strip(), PropertyListing(), False

    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return raw.strip(), PropertyListing(), False

    fields_data = data.get("fields")
    fields_data = fields_data if isinstance(fields_data, dict) else {}

    return reply.strip(), _to_property_listing(fields_data), data.get("handoff_requested") is True


SEEN_MESSAGE_TTL_SECONDS = 600


@dataclass(frozen=True)
class BotConfig:
    enabled: bool
    max_history_turns: int
    system_prompt: str


def load_bot_config() -> BotConfig:
    """Carga la configuración del bot desde variables de entorno."""
    enabled = (os.getenv("WHATSAPP_BOT_ENABLED") or "").strip().lower() in ("1", "true", "yes")
    max_history_turns = int((os.getenv("WHATSAPP_BOT_MAX_HISTORY_TURNS") or "6").strip())
    system_prompt = (os.getenv("WHATSAPP_BOT_SYSTEM_PROMPT") or "").strip() or DEFAULT_SYSTEM_PROMPT
    return BotConfig(enabled=enabled, max_history_turns=max_history_turns, system_prompt=system_prompt)


DEFAULT_DB_PATH = os.getenv("WHATSAPP_BOT_DB_PATH", "data/whatsapp_bot.db")


@dataclass
class ConversationStore:
    """Historial + cache de deal_id por chat, persistidos en SQLite; dedup de mensajes en memoria.

    `db_path=":memory:"` (default) da una base aislada por instancia — lo
    que quieren los tests. El singleton de proceso (`conversation_store`,
    más abajo) usa un archivo real para sobrevivir a un restart/deploy.
    """

    max_history_turns: int = 6
    db_path: str = ":memory:"
    _seen_message_ids: dict[str, float] = field(default_factory=dict)
    _conn: Any = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self._conn = store_db.init_db(self.db_path)

    def already_processed(self, message_id: str) -> bool:
        self._purge_expired_seen()
        return message_id in self._seen_message_ids

    def mark_processed(self, message_id: str) -> None:
        self._seen_message_ids[message_id] = time.monotonic()

    def _purge_expired_seen(self) -> None:
        cutoff = time.monotonic() - SEEN_MESSAGE_TTL_SECONDS
        expired = [mid for mid, seen_at in self._seen_message_ids.items() if seen_at < cutoff]
        for mid in expired:
            del self._seen_message_ids[mid]

    def get_history(self, chat_id: str) -> list[dict[str, str]]:
        return store_db.get_history(self._conn, chat_id, self.max_history_turns * 2)

    def add_turn(self, chat_id: str, role: str, content: str) -> None:
        store_db.add_turn(self._conn, chat_id, role, content, self.max_history_turns * 2)

    def get_deal_id(self, chat_id: str) -> str | None:
        return store_db.get_deal_id(self._conn, chat_id)

    def set_deal_id(self, chat_id: str, deal_id: str) -> None:
        store_db.set_deal_id(self._conn, chat_id, deal_id)


# Singleton a nivel de proceso: un archivo SQLite real, sobrevive a un restart.
conversation_store = ConversationStore(db_path=DEFAULT_DB_PATH)


def _resolve_deal_id(
    chat_id: str, crm_client: CrmClient, waha_client: WahaClient, session: str, sender_name: str | None
) -> str | None:
    """Resuelve (o crea) el deal de consignación de Bitrix para este chat de WhatsApp.

    El identificador normal es el teléfono (`from_chat_id`). Si WhatsApp
    oculta el número del remitente, el chat llega como `@lid` en vez de
    `@c.us` — en ese caso primero se intenta resolver el teléfono real vía
    `WahaClient.resolve_lid_to_phone` (Waha lo sabe si ya compartió un
    grupo o chat directo con este número antes); si Waha tampoco lo sabe
    todavía, se usa el identificador `@lid` como respaldo
    (`lid_from_chat_id`, guardado en `fields.FIELD_USERNAME`), para no
    perder el hilo con esos clientes aunque no se pueda crear el contacto
    sin teléfono (ver `CrmClient.find_or_create_property_seller_contact`).
    """
    phone = from_chat_id(chat_id)
    username = None

    if phone is None:
        username = lid_from_chat_id(chat_id)
        if username is not None:
            resolved_chat_id = waha_client.resolve_lid_to_phone(username, session=session)
            if resolved_chat_id is not None:
                phone = from_chat_id(resolved_chat_id)

    if phone is None and username is None:
        logger.warning("chat_id %s no es un chat @c.us ni @lid reconocible, no se vincula a Bitrix", chat_id)
        return None

    contact_id = crm_client.find_or_create_property_seller_contact(phone, username, sender_name)
    if contact_id is None:
        if phone is None:
            # Esperado: sin teléfono no se puede crear el contacto (ver
            # CrmClient.find_or_create_property_seller_contact) — el bot
            # sigue respondiendo por WhatsApp, solo no queda nada en Bitrix.
            logger.info(
                "Chat %s sin teléfono (solo @lid) y sin contacto existente en Bitrix, no se vincula esta vez",
                chat_id,
            )
        else:
            logger.error("No se pudo resolver/crear contacto en Bitrix para %s", phone)
        return None

    deal_id = crm_client.find_or_create_property_seller_deal(contact_id)
    if deal_id is None:
        logger.error("No se pudo resolver/crear deal de consignación para contacto %s", contact_id)
    return deal_id


def process(
    inbound: InboundMessage,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    config: BotConfig | None = None,
    store: ConversationStore | None = None,
) -> dict[str, Any]:
    """Procesa un mensaje entrante de WhatsApp y responde vía LLM, guardando el inmueble en el CRM."""
    config = config or load_bot_config()
    store = store or conversation_store

    if not config.enabled:
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_disabled"}

    if store.already_processed(inbound.message_id):
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "duplicate_message"}
    store.mark_processed(inbound.message_id)

    deal_id = store.get_deal_id(inbound.chat_id)
    if deal_id is None:
        deal_id = _resolve_deal_id(inbound.chat_id, crm_client, waha_client, inbound.session, inbound.sender_name)
        if deal_id is not None:
            store.set_deal_id(inbound.chat_id, deal_id)

    if deal_id is not None and not crm_client.get_bot_active(deal_id):
        logger.info("Bot pausado para el deal %s (chat %s), no se responde", deal_id, inbound.chat_id)
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_paused"}

    listing = crm_client.get_property_listing(deal_id) if deal_id is not None else PropertyListing()

    history = store.get_history(inbound.chat_id)
    system_prompt = _build_system_prompt(config.system_prompt, listing)
    raw_output = llm_client.reply(system_prompt, history, inbound.text)
    if raw_output is None:
        logger.error("LLM no devolvió respuesta para %s, no se envía nada", inbound.chat_id)
        return {"ok": False, "chat_id": inbound.chat_id, "error": "llm_failed"}

    reply_text, extracted, handoff_requested = _parse_llm_output(raw_output)

    sent = waha_client.send_text(inbound.chat_id, reply_text, session=inbound.session)
    if sent:
        store.add_turn(inbound.chat_id, "user", inbound.text)
        store.add_turn(inbound.chat_id, "assistant", reply_text)
        if deal_id is not None and extracted != PropertyListing():
            crm_client.update_property_listing(deal_id, extracted)
        if deal_id is not None and handoff_requested:
            crm_client.set_bot_active(deal_id, False)
            crm_client.add_comment(deal_id, "Bot: cliente pidió hablar con un asesor, bot pausado automáticamente.")

    return {"ok": sent, "chat_id": inbound.chat_id, "reply": reply_text}
