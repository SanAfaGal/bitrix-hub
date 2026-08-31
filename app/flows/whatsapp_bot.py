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

Para pruebas en desarrollo, `WHATSAPP_BOT_ALLOWED_NUMBERS` (lista separada
por comas, mismo formato que devuelve `app.waha.phone.from_chat_id` —
código de país + número, sin `+`) restringe las respuestas a esos números
únicamente; vacío (default) no restringe nada.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any

from app.crm.protocol import CrmClient, PropertyListing
from app.flows import whatsapp_bot_store as store_db
from app.flows.whatsapp_bot_welcome import maybe_send_first_contact_welcome
from app.forms.models import PROPERTY_TYPES
from app.llm.client import LlmClient
from app.message_templates import store as templates_store
from app.transcription.client import TranscriptionClient
from app.waha.client import WahaClient
from app.waha.inbound import InboundMessage
from app.waha.phone import from_chat_id, lid_from_chat_id, to_chat_id

logger = logging.getLogger(__name__)

_OUTPUT_FORMAT_INSTRUCTIONS = (
    "\n\nFormato de salida (obligatorio, sin excepción): responda ÚNICAMENTE "
    "con un objeto JSON válido, sin texto antes ni después, con esta forma "
    'exacta:\n{"reply": "<el mensaje que se le manda a la persona por '
    'WhatsApp>", "fields": {"property_type": <uno de ' + repr(list(PROPERTY_TYPES)) + " o null>, "
    '"address": <string o null>, "sector_zone_city": <string o null>, '
    '"expected_sale_price": <número entero o null>, "registration_number": '
    '<string o null>}, "client_full_name": <nombre y apellido de la persona, '
    'string o null>, "client_phone": <teléfono de la persona, string o '
    'null>, "proposed_full_name": <string o null>, "proposed_phone": '
    '<string o null>, "handoff_requested": <true o false>}\n'
    'En "fields" solo van los datos que la persona haya mencionado o '
    'confirmado en ESTE turno — todo lo demás va en null, aunque ya lo '
    "sepamos de antes. No repita en \"fields\" un dato que ya aparece en la "
    'lista de "Datos que ya tenemos" salvo que la persona lo esté '
    "corrigiendo. Lo mismo aplica a \"client_full_name\" y \"client_phone\": "
    "solo van si la persona los dijo/confirmó en ESTE turno, null en "
    "cualquier otro caso — incluyendo cuando ya están confirmados.\n"
    '"proposed_full_name" y "proposed_phone" van cuando, en "reply", usted '
    "le está preguntando a la persona si un nombre o teléfono es correcto "
    "(sea porque la persona lo acaba de escribir, o porque usted se lo "
    "propuso a partir del perfil de WhatsApp o el número del chat) — van "
    "con el valor exacto que usted está proponiéndole confirmar, en "
    "cualquier otro turno van en null.\n"
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


def _identity_block(
    confirmed_name: str | None,
    confirmed_phone: str | None,
    candidate_name: str | None = None,
    candidate_phone: str | None = None,
) -> str:
    def fmt(value: str | None) -> str:
        return value if value else "(no confirmado)"

    lines = [
        "Datos de contacto de la persona:",
        f"- Nombre completo: {fmt(confirmed_name)}",
        f"- Teléfono: {fmt(confirmed_phone)}",
    ]
    if confirmed_name is None and candidate_name:
        lines.append(
            f"- Nombre de perfil de WhatsApp (sin confirmar, pregúntele si es el suyo): {candidate_name}"
        )
    if confirmed_phone is None and candidate_phone:
        lines.append(
            f"- Teléfono detectado del chat (sin confirmar, pregúntele si es correcto): {candidate_phone}"
        )
    return "\n".join(lines)


def _build_system_prompt(
    base_prompt: str,
    listing: PropertyListing,
    confirmed_name: str | None,
    confirmed_phone: str | None,
    candidate_name: str | None = None,
    candidate_phone: str | None = None,
) -> str:
    return (
        f"{base_prompt}\n\n{_identity_block(confirmed_name, confirmed_phone, candidate_name, candidate_phone)}"
        f"\n\n{_known_fields_block(listing)}{_OUTPUT_FORMAT_INSTRUCTIONS}"
    )


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


@dataclass(frozen=True)
class LlmTurn:
    """Resultado de parsear un turno de respuesta del LLM."""

    reply: str
    listing: PropertyListing
    handoff_requested: bool = False
    client_full_name: str | None = None
    client_phone: str | None = None
    proposed_full_name: str | None = None
    proposed_phone: str | None = None


def _parse_llm_output(raw: str) -> LlmTurn:
    """Parsea la salida del LLM (JSON `{"reply": ..., "fields": ..., "handoff_requested": ...,
    "client_full_name": ..., "client_phone": ...}`).

    Si el LLM no devolvió JSON válido (algún proveedor puede ignorar la
    instrucción), se trata todo el texto como la respuesta a mandar, no se
    actualiza ningún campo y no se pide handoff ni identidad — nunca se
    rompe la conversación por esto.
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
        return LlmTurn(reply=raw.strip(), listing=PropertyListing())

    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return LlmTurn(reply=raw.strip(), listing=PropertyListing())

    fields_data = data.get("fields")
    fields_data = fields_data if isinstance(fields_data, dict) else {}

    return LlmTurn(
        reply=reply.strip(),
        listing=_to_property_listing(fields_data),
        handoff_requested=data.get("handoff_requested") is True,
        client_full_name=_as_text(data.get("client_full_name")),
        client_phone=_as_text(data.get("client_phone")),
        proposed_full_name=_as_text(data.get("proposed_full_name")),
        proposed_phone=_as_text(data.get("proposed_phone")),
    )


SEEN_MESSAGE_TTL_SECONDS = 600
RATE_LIMIT_COOLDOWN_SECONDS = 5  # Max 1 msg every 5 seconds per chat


@dataclass(frozen=True)
class BotConfig:
    enabled: bool
    max_history_turns: int
    allowed_numbers: frozenset[str] = frozenset()


def load_bot_config() -> BotConfig:
    """Carga la configuración del bot desde variables de entorno.

    El system prompt ya no viene de acá — se edita desde el panel admin
    (`app/message_templates/store.py`, key `whatsapp_system_prompt`).
    """
    enabled = (os.getenv("WHATSAPP_BOT_ENABLED") or "").strip().lower() in ("1", "true", "yes")
    max_history_turns = int((os.getenv("WHATSAPP_BOT_MAX_HISTORY_TURNS") or "6").strip())
    allowed_numbers = frozenset(
        n.strip() for n in (os.getenv("WHATSAPP_BOT_ALLOWED_NUMBERS") or "").split(",") if n.strip()
    )
    return BotConfig(
        enabled=enabled,
        max_history_turns=max_history_turns,
        allowed_numbers=allowed_numbers,
    )


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
    _last_message_time: dict[str, float] = field(default_factory=dict)
    _conn: Any = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self._conn = store_db.init_db(self.db_path)

    def already_processed(self, message_id: str) -> bool:
        self._purge_expired_seen()
        return message_id in self._seen_message_ids

    def mark_processed(self, message_id: str) -> None:
        self._seen_message_ids[message_id] = time.monotonic()

    def is_rate_limited(self, chat_id: str) -> bool:
        """Retorna True si el chat está en cooldown (más de 1 msg en últimos 5 seg)."""
        now = time.monotonic()
        if chat_id in self._last_message_time:
            elapsed = now - self._last_message_time[chat_id]
            if elapsed < RATE_LIMIT_COOLDOWN_SECONDS:
                return True
        return False

    def mark_message_received(self, chat_id: str) -> None:
        """Registra que recibimos un mensaje de este chat para rate limiting."""
        self._last_message_time[chat_id] = time.monotonic()

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

    def clear_deal_id(self, chat_id: str) -> None:
        store_db.clear_deal_id(self._conn, chat_id)

    def get_confirmed_identity(self, chat_id: str) -> tuple[str | None, str | None]:
        return store_db.get_confirmed_identity(self._conn, chat_id)

    def set_confirmed_name(self, chat_id: str, name: str) -> None:
        store_db.set_confirmed_name(self._conn, chat_id, name)

    def set_confirmed_phone(self, chat_id: str, phone: str) -> None:
        store_db.set_confirmed_phone(self._conn, chat_id, phone)

    def get_pending_identity(self, chat_id: str) -> tuple[str | None, str | None]:
        return store_db.get_pending_identity(self._conn, chat_id)

    def set_pending_name(self, chat_id: str, name: str) -> None:
        store_db.set_pending_name(self._conn, chat_id, name)

    def set_pending_phone(self, chat_id: str, phone: str) -> None:
        store_db.set_pending_phone(self._conn, chat_id, phone)

    def clear_pending_identity(self, chat_id: str) -> None:
        store_db.clear_pending_identity(self._conn, chat_id)


# Singleton a nivel de proceso: un archivo SQLite real, sobrevive a un restart.
conversation_store = ConversationStore(db_path=DEFAULT_DB_PATH)


def _resolve_phone(chat_id: str, waha_client: WahaClient, session: str) -> tuple[str | None, str | None]:
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


def _create_deal_from_confirmed_identity(
    chat_id: str, crm_client: CrmClient, store: ConversationStore
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

    deal_id = crm_client.find_or_create_property_seller_deal(contact_id)
    if deal_id is not None:
        store.set_deal_id(chat_id, deal_id)
    return deal_id


def _resolve_text(
    inbound: InboundMessage, waha_client: WahaClient, transcription_client: TranscriptionClient
) -> str | None:
    """Si el mensaje es texto lo retorna tal cual; si es una nota de voz, la descarga y transcribe.

    Retorna `None` si no se pudo obtener texto (falló la descarga del audio
    o la transcripción) — el caller decide qué responder en ese caso.
    """
    if not inbound.is_audio:
        return inbound.text
    if not inbound.audio_media_path:
        return None
    audio_bytes = waha_client.download_media(inbound.audio_media_path)
    if audio_bytes is None:
        return None
    return transcription_client.transcribe(audio_bytes)


def process(
    inbound: InboundMessage,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    transcription_client: TranscriptionClient,
    config: BotConfig | None = None,
    store: ConversationStore | None = None,
) -> dict[str, Any]:
    """Procesa un mensaje entrante de WhatsApp y responde vía LLM, guardando el inmueble en el CRM."""
    config = config or load_bot_config()
    store = store or conversation_store

    if not config.enabled:
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_disabled"}

    if config.allowed_numbers:
        phone, _ = _resolve_phone(inbound.chat_id, waha_client, inbound.session)
        if phone not in config.allowed_numbers:
            logger.info("Chat %s fuera de WHATSAPP_BOT_ALLOWED_NUMBERS, no se responde", inbound.chat_id)
            return {"ok": True, "chat_id": inbound.chat_id, "skipped": "number_not_allowed"}

    if store.already_processed(inbound.message_id):
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "duplicate_message"}
    store.mark_processed(inbound.message_id)

    if store.is_rate_limited(inbound.chat_id):
        logger.info("Chat %s rate limited, no se responde", inbound.chat_id)
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "rate_limited"}
    store.mark_message_received(inbound.chat_id)

    if maybe_send_first_contact_welcome(inbound.chat_id, inbound.session, waha_client, crm_client, store):
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "first_contact_welcome"}

    if inbound.is_unsupported:
        logger.info("Mensaje con media no soportada de %s, se pide que escriba", inbound.chat_id)
        waha_client.send_text(
            inbound.chat_id, templates_store.get_template("whatsapp_unsupported_message"), session=inbound.session
        )
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "unsupported_media"}

    text = _resolve_text(inbound, waha_client, transcription_client)
    if text is None:
        logger.info("No se pudo transcribir el audio de %s, se pide que escriba", inbound.chat_id)
        waha_client.send_text(
            inbound.chat_id, templates_store.get_template("whatsapp_transcription_failed"), session=inbound.session
        )
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "transcription_failed"}
    inbound = replace(inbound, text=text)

    deal_id = store.get_deal_id(inbound.chat_id)
    if deal_id is not None and not crm_client.deal_exists(deal_id):
        logger.info("Deal cacheado %s (chat %s) ya no existe en el CRM, se resuelve uno nuevo", deal_id, inbound.chat_id)
        store.clear_deal_id(inbound.chat_id)
        deal_id = None

    if deal_id is not None and not crm_client.get_bot_active(deal_id):
        logger.info("Bot pausado para el deal %s (chat %s), no se responde", deal_id, inbound.chat_id)
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_paused"}

    if deal_id is None:
        _maybe_promote_pending_identity(inbound.chat_id, inbound.text, store)
        deal_id = _create_deal_from_confirmed_identity(inbound.chat_id, crm_client, store)

    listing = crm_client.get_property_listing(deal_id) if deal_id is not None else PropertyListing()
    confirmed_name, confirmed_phone = store.get_confirmed_identity(inbound.chat_id)

    # Sin deal todavía (identidad sin confirmar): se le muestran al LLM
    # candidatos de nombre/teléfono "fáciles de conseguir" (perfil de
    # WhatsApp, número del chat) para que los confirme con la persona en
    # vez de pedirlos de cero — nunca se dan por buenos sin que la persona
    # los confirme en el chat (eso sigue pasando en _apply_confirmed_identity).
    candidate_name: str | None = None
    candidate_phone: str | None = None
    if deal_id is None:
        candidate_name = inbound.sender_name
        candidate_phone, _ = _resolve_phone(inbound.chat_id, waha_client, inbound.session)

    history = store.get_history(inbound.chat_id)
    system_prompt = _build_system_prompt(
        templates_store.get_template("whatsapp_system_prompt"),
        listing,
        confirmed_name,
        confirmed_phone,
        candidate_name,
        candidate_phone,
    )
    raw_output = llm_client.reply(system_prompt, history, inbound.text)
    if raw_output is None:
        logger.error("LLM no devolvió respuesta para %s, no se envía nada", inbound.chat_id)
        return {"ok": False, "chat_id": inbound.chat_id, "error": "llm_failed"}

    turn = _parse_llm_output(raw_output)

    sent = waha_client.send_text(inbound.chat_id, turn.reply, session=inbound.session)
    if sent:
        store.add_turn(inbound.chat_id, "user", inbound.text)
        store.add_turn(inbound.chat_id, "assistant", turn.reply)

        deal_id = _apply_confirmed_identity(inbound.chat_id, turn, deal_id, crm_client, store)

        if deal_id is None:
            _capture_pending_identity(inbound.chat_id, turn, store)

        if deal_id is not None and turn.listing != PropertyListing():
            crm_client.update_property_listing(deal_id, turn.listing)
        if deal_id is not None and turn.handoff_requested:
            crm_client.set_bot_active(deal_id, False)
            crm_client.add_comment(deal_id, "Bot: cliente pidió hablar con un asesor, bot pausado automáticamente.")

    return {"ok": sent, "chat_id": inbound.chat_id, "reply": turn.reply}


_AFFIRMATION_RE = re.compile(
    r"^(s[ií]|correcto|exacto|as[ií] es|as[ií] mismo|eso es|confirmo|claro que s[ií])\W*$",
    re.IGNORECASE,
)


def _normalize_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    chat_id_form = to_chat_id(raw)
    return from_chat_id(chat_id_form) if chat_id_form else None


def _maybe_promote_pending_identity(chat_id: str, text: str, store: ConversationStore) -> None:
    """Promueve a confirmado el nombre/teléfono que el bot propuso en su mensaje anterior.

    Red de seguridad para cuando la persona confirma con un simple "sí" y
    el LLM no repite esos valores en `client_full_name`/`client_phone` de
    ese mismo turno (`proposed_full_name`/`proposed_phone`, guardados en el
    turno anterior vía `_capture_pending_identity`, cubren ese hueco).
    """
    confirmed_name, confirmed_phone = store.get_confirmed_identity(chat_id)
    if confirmed_name is not None and confirmed_phone is not None:
        return
    if not _AFFIRMATION_RE.match(text.strip()):
        return

    pending_name, pending_phone = store.get_pending_identity(chat_id)
    if pending_name is None and pending_phone is None:
        return

    if confirmed_name is None and pending_name is not None:
        store.set_confirmed_name(chat_id, pending_name)
    if confirmed_phone is None and pending_phone is not None:
        store.set_confirmed_phone(chat_id, pending_phone)
    store.clear_pending_identity(chat_id)


def _capture_pending_identity(chat_id: str, turn: LlmTurn, store: ConversationStore) -> None:
    """Guarda el nombre/teléfono que el bot le acaba de proponer a la persona para confirmar."""
    if turn.proposed_full_name is not None:
        store.set_pending_name(chat_id, turn.proposed_full_name)

    normalized_phone = _normalize_phone(turn.proposed_phone)
    if normalized_phone is not None:
        store.set_pending_phone(chat_id, normalized_phone)


def _apply_confirmed_identity(
    chat_id: str, turn: LlmTurn, deal_id: str | None, crm_client: CrmClient, store: ConversationStore
) -> str | None:
    """Guarda el nombre/teléfono que la persona confirmó en este turno, en el store y en Bitrix.

    Sin deal todavía, no crea nada en Bitrix hasta que el store tenga
    nombre Y teléfono confirmados (no alcanza con uno de los dos, ni con
    que se hayan confirmado en turnos distintos) — así no quedan
    negociaciones a medio llenar visibles para un asesor. Si el contacto
    ya existe (deal ya creado), en cambio, cualquier confirmación nueva se
    aplica de una (backfill de un contacto creado antes solo con
    `username`, o corrección del nombre). Retorna el `deal_id` vigente
    (puede ser uno nuevo, si se acaba de crear).
    """
    normalized_phone = _normalize_phone(turn.client_phone)
    if normalized_phone is not None:
        store.set_confirmed_phone(chat_id, normalized_phone)

    if turn.client_full_name is not None:
        store.set_confirmed_name(chat_id, turn.client_full_name)

    if normalized_phone is None and turn.client_full_name is None:
        return deal_id

    if deal_id is None:
        return _create_deal_from_confirmed_identity(chat_id, crm_client, store)

    contact_id = crm_client.get_deal_contact_id(crm_client.get_deal(deal_id))
    if contact_id is not None:
        crm_client.update_contact_identity(contact_id, phone=normalized_phone, full_name=turn.client_full_name)
    return deal_id
