"""Bot conversacional de WhatsApp — Waha (entrante) + LLM (app/llm/, cualquier proveedor compatible con OpenAI) + CRM.

**Experimental.** Combina tres integraciones (Waha + LLM + CRM), por eso
vive acá y no en `app/waha/` — ver `app/flows/README.md`. Apagado por
defecto (`WHATSAPP_BOT_ENABLED=false`); mientras esté apagado, el endpoint
sigue existiendo pero no llama al LLM ni responde.

Los datos del inmueble que el cliente cuenta (tipo, dirección, sector/zona/
ciudad, precio esperado, matrícula) se guardan directo en el deal de
consignación en Bitrix (`app.crm.protocol.PropertyListing`) — esa es la
fuente de verdad. El historial de turnos y el `deal_id` por chat
(`ConversationStore`) se persisten en MySQL (`whatsapp_bot_store.py`,
`whatsapp_bot_db.py`) y sobreviven a un restart/deploy — solo el dedup de
mensajes reintentados por Waha queda en memoria del proceso (un TTL corto,
sin problema si se pierde).

Un `threading.Lock` por `chat_id` (`ConversationStore.chat_lock`) serializa
`process()` para un mismo chat — sin esto, dos mensajes que llegan casi
simultáneos para el mismo chat (ej. WhatsApp entrega uno por teléfono y
otro por `@lid` casi a la vez) corren en threads distintos
(`asyncio.to_thread` en `app.waha.router`), ambos ven `deal_id is None`
antes de que cualquiera termine de crearlo, y cada uno crea su propio deal
duplicado en Bitrix (visto en producción: dos "Deal de consignación
creado..." para el mismo contacto, 400ms aparte).

Si un asesor pausa el bot para un deal puntual (checkbox en Bitrix,
`fields.FIELD_BOT_ACTIVE`), o el bot mismo lo pausa al detectar que la
persona pidió hablar con un humano, el webhook deja de responder para ese
chat hasta que el campo se reactive manualmente.

La nota de voz que explica el proceso nunca se manda sola: primero se
pregunta si la persona la quiere (`whatsapp_offer_explanation`, ver
`whatsapp_bot_welcome.py`/`whatsapp_bot_explanation.py`) y solo se envía si
confirma — si declina, el bot no vuelve a ofrecerla ni avanza por su
cuenta al link de Autorización, pero se la manda igual si la pide después
en cualquier turno (`LlmTurn.explanation_requested`,
`maybe_handle_delayed_explanation_request`). Si el cliente afirma en el
chat que ya firmó la Autorización de Corretaje (`LlmTurn.signed_claim`)
pero el campo de Bitrix todavía no dice `"firmada"`, el bot se lo aclara y
reenvía el link en vez de darlo por bueno.

Para pruebas en desarrollo, `WHATSAPP_BOT_ALLOWED_NUMBERS` (lista separada
por comas, mismo formato que devuelve `app.waha.phone.from_chat_id` —
código de país + número, sin `+`) restringe las respuestas a esos números
únicamente; vacío (default) no restringe nada.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from typing import Any

from app.crm.protocol import CrmClient, PropertyListing
from app.flows import whatsapp_bot_db as store_engine
from app.flows.settings import load_public_base_url
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.flows.whatsapp_bot_conversation_store import ConversationStore
from app.flows.whatsapp_bot_explanation import (
    maybe_handle_acceptance,
    maybe_handle_delayed_explanation_request,
    maybe_handle_explanation_response,
    maybe_send_explanation,
)
from app.flows.whatsapp_bot_llm import (
    AFFIRMATION_RE as _AFFIRMATION_RE,
    LlmTurn,
    _awaiting_acceptance_note,
    _build_system_prompt,
    _parse_llm_output,
)
from app.flows.whatsapp_bot_welcome import maybe_send_first_contact_welcome
from app.forms.settings import load_form_link_secret
from app.llm.client import LlmClient
from app.message_templates import store as templates_store
from app.transcription.client import TranscriptionClient
from app.waha.client import WahaClient
from app.waha.inbound import InboundMessage
from app.waha.phone import from_chat_id, lid_from_chat_id, to_chat_id

logger = logging.getLogger(__name__)


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


# Singleton a nivel de proceso: el MySQL real, sobrevive a un restart. Ver
# `ConversationStore` en `whatsapp_bot_conversation_store.py`.
conversation_store = ConversationStore(engine=store_engine.engine)


def _resolve_authorization_link_config(
    public_base_url: str | None, link_secret: str | None
) -> tuple[str | None, str | None]:
    """Resuelve `(public_base_url, link_secret)` para el link de Autorización, cargando de env si falta alguno."""
    resolved_base_url = public_base_url
    resolved_secret = link_secret
    if resolved_base_url is None or resolved_secret is None:
        try:
            resolved_base_url = resolved_base_url or load_public_base_url()
            resolved_secret = resolved_secret or load_form_link_secret()
        except RuntimeError:
            logger.error(
                "Bot de WhatsApp: falta HUB_PUBLIC_BASE_URL/FORM_LINK_SECRET, no se puede mandar el link de Autorización"
            )
            return None, None
    return resolved_base_url, resolved_secret


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
    public_base_url: str | None = None,
    link_secret: str | None = None,
) -> dict[str, Any]:
    """Procesa un mensaje entrante de WhatsApp y responde vía LLM, guardando el inmueble en el CRM.

    Serializado por `store.chat_lock(inbound.chat_id)` — ver el docstring
    del módulo sobre la creación de deals duplicados que esto evita.
    """
    store = store or conversation_store
    with store.chat_lock(inbound.chat_id):
        return _process(inbound, waha_client, llm_client, crm_client, transcription_client, config, store, public_base_url, link_secret)


def _process(
    inbound: InboundMessage,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    transcription_client: TranscriptionClient,
    config: BotConfig | None,
    store: ConversationStore,
    public_base_url: str | None,
    link_secret: str | None,
) -> dict[str, Any]:
    """Cuerpo de `process()`, corre siempre dentro del `chat_lock` del chat.

    `public_base_url`/`link_secret` son para el link de la Autorización de
    Corretaje (`maybe_handle_acceptance`) — si no se pasan (caso normal en
    producción), se cargan de `HUB_PUBLIC_BASE_URL`/`FORM_LINK_SECRET` acá
    mismo, la primera vez que hacen falta.
    """
    config = config or load_bot_config()

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

    if store.get_explanation_offered(inbound.chat_id) and not store.get_explanation_sent(inbound.chat_id):
        if maybe_handle_explanation_response(inbound.chat_id, inbound.text, waha_client, inbound.session, store):
            return {"ok": True, "chat_id": inbound.chat_id, "skipped": "explanation_response_handled"}
        # Sin `explanation_declined` persistido, no hay forma de distinguir acá "todavía no
        # respondió la oferta" de "ya dijo que no y ahora habla de otra cosa" — forzar una nota
        # de "consiga un sí/no" en el segundo caso lo trababa insistiendo con el audio sin parar
        # (el mismo patrón de bug de `awaiting_acceptance`/autorización, visto en producción).
        # Se deja en manos del LLM, que ya ve el ofrecimiento + la respuesta en el historial.

    deal_id = store.get_deal_id(inbound.chat_id)
    if deal_id is not None and not crm_client.deal_exists(deal_id):
        logger.info("Deal cacheado %s (chat %s) ya no existe en el CRM, se resuelve uno nuevo", deal_id, inbound.chat_id)
        store.clear_deal_id(inbound.chat_id)
        deal_id = None

    if deal_id is not None and not crm_client.get_bot_active(deal_id):
        logger.info("Bot pausado para el deal %s (chat %s), no se responde", deal_id, inbound.chat_id)
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_paused"}

    deal_id_before_identity_resolution = deal_id
    if deal_id is None:
        deal_id = _create_deal_from_confirmed_identity(inbound.chat_id, crm_client, store)

    awaiting_acceptance = False
    if deal_id is not None and store.get_explanation_sent(inbound.chat_id):
        if not store.get_authorization_link_sent(inbound.chat_id):
            resolved_base_url, resolved_secret = _resolve_authorization_link_config(public_base_url, link_secret)

            if resolved_base_url and resolved_secret and maybe_handle_acceptance(
                inbound.chat_id,
                inbound.text,
                deal_id,
                crm_client,
                waha_client,
                inbound.session,
                resolved_base_url,
                resolved_secret,
                store,
            ):
                return {"ok": True, "chat_id": inbound.chat_id, "skipped": "authorization_link_sent"}

            awaiting_acceptance = True

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
        confirmed_name,
        confirmed_phone,
        candidate_name,
        candidate_phone,
    )
    if awaiting_acceptance:
        system_prompt += _awaiting_acceptance_note()
    raw_output = llm_client.reply(system_prompt, history, inbound.text)
    if raw_output is None:
        logger.error("LLM no devolvió respuesta para %s, no se envía nada", inbound.chat_id)
        return {"ok": False, "chat_id": inbound.chat_id, "error": "llm_failed"}

    turn = _parse_llm_output(raw_output)

    if deal_id is not None and turn.signed_claim:
        deal = crm_client.get_deal(deal_id)
        if crm_client.get_authorization_status(deal) != "firmada":
            resolved_base_url, resolved_secret = _resolve_authorization_link_config(public_base_url, link_secret)
            if resolved_base_url and resolved_secret:
                clarification = templates_store.get_template("whatsapp_authorization_not_received_yet")
                waha_client.send_text(inbound.chat_id, clarification, session=inbound.session)
                process_welcome_and_authorization(
                    deal_id, crm_client, waha_client, resolved_base_url, resolved_secret, session=inbound.session
                )
                store.add_turn(inbound.chat_id, "user", inbound.text)
                store.add_turn(inbound.chat_id, "assistant", clarification)
                return {"ok": True, "chat_id": inbound.chat_id, "skipped": "signed_claim_not_yet_received"}

    sent = waha_client.send_text(inbound.chat_id, turn.reply, session=inbound.session)
    if sent:
        store.add_turn(inbound.chat_id, "user", inbound.text)
        store.add_turn(inbound.chat_id, "assistant", turn.reply)

        deal_id = _apply_confirmed_identity(inbound.chat_id, turn, deal_id, crm_client, store)

        if deal_id is not None and turn.listing != PropertyListing():
            crm_client.update_property_listing(deal_id, turn.listing)
        if deal_id is not None and turn.handoff_requested:
            crm_client.set_bot_active(deal_id, False)
            crm_client.add_comment(deal_id, "Bot: cliente pidió hablar con un asesor, bot pausado automáticamente.")

        if deal_id_before_identity_resolution is None and deal_id is not None:
            if not maybe_send_explanation(inbound.chat_id, inbound.session, waha_client, store):
                # Cliente conocido: la explicación ya se había ofrecido/mandado antes de
                # confirmar identidad (`whatsapp_bot_welcome.py`), así que la afirmación
                # original a `whatsapp_ask_acceptance` se perdió respondiendo nombre/teléfono
                # en su lugar. El deal recién se crea acá — hay que volver a pedirla, si no
                # la conversación queda esperando sin que el bot pida nada.
                if store.get_explanation_sent(inbound.chat_id) and not store.get_authorization_link_sent(
                    inbound.chat_id
                ):
                    resolved_base_url, resolved_secret = _resolve_authorization_link_config(
                        public_base_url, link_secret
                    )
                    if resolved_base_url and resolved_secret:
                        ask_text = templates_store.get_template("whatsapp_ask_acceptance")
                        if waha_client.send_text(inbound.chat_id, ask_text, session=inbound.session):
                            store.add_turn(inbound.chat_id, "assistant", ask_text)

        maybe_handle_delayed_explanation_request(
            inbound.chat_id, turn.explanation_requested, waha_client, inbound.session, store
        )

    return {"ok": sent, "chat_id": inbound.chat_id, "reply": turn.reply}


def _normalize_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    chat_id_form = to_chat_id(raw)
    return from_chat_id(chat_id_form) if chat_id_form else None


def _apply_confirmed_identity(
    chat_id: str, turn: LlmTurn, deal_id: str | None, crm_client: CrmClient, store: ConversationStore
) -> str | None:
    """Si el LLM ya tiene nombre Y teléfono confirmados en este turno, los guarda juntos (nunca
    uno solo — ver `ConversationStore.set_confirmed_identity`) y crea el deal. El LLM es quien
    lleva la cuenta de qué ya se confirmó en turnos anteriores (ve el historial completo) y
    repite ambos datos en el mismo turno la primera vez que tiene los dos, aunque uno se haya
    confirmado antes — así no hace falta persistir un estado "a medias" acá.

    Si el deal ya existe, en cambio, cualquier confirmación nueva (aunque sea una sola) se
    aplica directo en Bitrix (backfill de un contacto creado antes solo con `username`, o
    corrección del nombre/teléfono) — no hace falta esperar a tener los dos para eso. Retorna
    el `deal_id` vigente (puede ser uno nuevo, si se acaba de crear).
    """
    normalized_phone = _normalize_phone(turn.client_phone)

    if deal_id is None:
        if turn.client_full_name is not None and normalized_phone is not None:
            store.set_confirmed_identity(chat_id, turn.client_full_name, normalized_phone)
            return _create_deal_from_confirmed_identity(chat_id, crm_client, store)
        return deal_id

    if normalized_phone is None and turn.client_full_name is None:
        return deal_id

    contact_id = crm_client.get_deal_contact_id(crm_client.get_deal(deal_id))
    if contact_id is not None:
        crm_client.update_contact_identity(contact_id, phone=normalized_phone, full_name=turn.client_full_name)
    return deal_id
