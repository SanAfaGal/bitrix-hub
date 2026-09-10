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

Además del interruptor global, cada chat tiene su propia activación opt-in
(`ConversationStore.get_bot_enabled`/`set_bot_enabled`, columna `bot_enabled`
de `leads`) — apagada por default para todo chat, nuevo o viejo; un admin la
prende a mano desde el panel admin. Mientras esté apagada, `_process()` no
manda bienvenida, no transcribe audio ni llama al LLM (silencio total, para
que un asesor pueda seguir atendiendo el chat a mano por WhatsApp Web), pero
sí guarda el mensaje entrante (placeholder para audio/media no soportada,
ver `_placeholder_for_untranscribed_inbound`) — así el chat aparece en
`/admin/prospects` para que el admin sepa que hay que activarlo.

El bot también se autopausa a través del mismo `bot_enabled` cuando detecta
que la persona pidió hablar con un humano (`turn.handoff_requested`), o
cuando se firma la Autorización de Corretaje
(`app/flows/brokerage_authorization_signed.py`) — en ambos casos apaga el
chat vía `store.set_bot_enabled(chat_id, False)`, igual que si un admin lo
pausara desde el panel; para reactivarlo hay que volver a prenderlo desde
ahí, no hay reactivación automática.

Antes de la explicación, se le pregunta a la persona si su inmueble está en
Medellín o el Oriente antioqueño — única zona donde se gestiona este
proceso por ahora (`whatsapp_bot_zone.py`). Si responde que no, se le avisa
que un asesor aparte lo va a contactar y el bot se desactiva para ese chat
(`bot_enabled=False`). Solo si confirma la zona se sigue con la explicación
del proceso (texto + nota de voz), que se manda de una sola vez sin
preguntar antes si la quiere, apenas se conoce su identidad
(`whatsapp_bot_welcome.py`/`whatsapp_bot_explanation.py::maybe_send_explanation`).
Si la persona la pide explícitamente antes de que le llegue por ese camino
(ej. identidad todavía sin confirmar), se le manda igual
(`LlmTurn.explanation_requested`, `maybe_handle_delayed_explanation_request`).
Si el cliente afirma en el
chat que ya firmó la Autorización de Corretaje (`LlmTurn.signed_claim`)
pero el campo de Bitrix todavía no dice `"firmada"`, el bot se lo aclara y
reenvía el link en vez de darlo por bueno. Mientras el link ya se mandó
(`authorization_link_sent`) pero Bitrix no dice `"firmada"` todavía, cada
turno recuerda que falta firmar (`_awaiting_signature_note`) en vez de
volver al prompt genérico — sin esto una confirmación genérica de la
persona ("sí") se podía contestar como si el proceso ya hubiera avanzado.

Para pruebas en desarrollo, `WHATSAPP_BOT_ALLOWED_NUMBERS` (lista separada
por comas, mismo formato que devuelve `app.waha.phone.from_chat_id` —
código de país + número, sin `+`) restringe las respuestas a esos números
únicamente; vacío (default) no restringe nada.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, replace
from typing import Any

from app.crm.protocol import CrmClient, PropertyListing
from app.flows import whatsapp_bot_db as store_engine
from app.flows.settings import load_public_base_url
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.flows.whatsapp_bot_conversation_store import RATE_LIMIT_COOLDOWN_SECONDS, ConversationStore
from app.flows.whatsapp_bot_explanation import (
    maybe_handle_acceptance,
    maybe_handle_delayed_explanation_request,
    maybe_send_explanation,
)
from app.flows.whatsapp_bot_llm import (
    AFFIRMATION_RE as _AFFIRMATION_RE,
    LlmTurn,
    _awaiting_acceptance_note,
    _awaiting_signature_note,
    _awaiting_zone_note,
    _build_system_prompt,
    _parse_llm_output,
)
from app.flows.whatsapp_bot_new_chat_check import is_chat_new_in_waha
from app.flows.whatsapp_bot_welcome import maybe_send_first_contact_welcome
from app.flows.whatsapp_bot_zone import maybe_ask_zone, maybe_handle_zone_response
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
    # Tope de mensajes previos de WhatsApp (traídos de Waha, no del store
    # local) que se le pasan al LLM al analizar el historial de un chat
    # antes de activarlo — ver `whatsapp_bot_history_seed.py`. Contexto
    # suficiente sin costo/tiempo excesivo.
    history_analysis_limit: int = 40


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
    history_analysis_limit = int((os.getenv("WHATSAPP_BOT_HISTORY_ANALYSIS_LIMIT") or "40").strip())
    return BotConfig(
        enabled=enabled,
        max_history_turns=max_history_turns,
        allowed_numbers=allowed_numbers,
        history_analysis_limit=history_analysis_limit,
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

    deal_id = crm_client.find_or_create_property_seller_deal(contact_id, source="whatsapp")
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


# Placeholders de `_placeholder_for_untranscribed_inbound` — no son texto real del cliente,
# `reply_after_activation` los trata igual que un turno vacío (nada que contestar).
_UNANSWERABLE_PLACEHOLDERS = frozenset({"[Nota de voz]", "[Media no soportada]"})


def _placeholder_for_untranscribed_inbound(inbound: InboundMessage) -> str:
    """Texto a guardar en `messages` para audio/media no soportada mientras el bot está
    apagado para el chat (ver `process()`) — ahí `inbound.text` llega vacío porque la
    transcripción/el manejo de media no soportada están más abajo del return temprano de ese
    caso. Sin esto quedaba una fila con `content=""` en la tabla."""
    if inbound.is_audio:
        return "[Nota de voz]"
    if inbound.is_unsupported:
        return "[Media no soportada]"
    return inbound.text


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

    if not store.chat_exists(inbound.chat_id):
        # Primera vez que se ve este chat_id (todavía no hay lead local) — antes de crear el
        # lead y de que el gate de abajo lea `bot_enabled` (que para un chat sin fila da False,
        # el default), se consulta Waha UNA sola vez para decidir la activación inicial: si el
        # cliente/asesor ya venían hablando ahí desde antes (Waha con historial previo, o la
        # consulta falla) el chat queda apagado como hoy, esperando activación manual; si es
        # una conversación genuinamente nueva, se auto-activa y este mismo mensaje ya se
        # responde normal, sin que un admin tenga que hacer nada. En mensajes siguientes de este
        # mismo chat `chat_exists` ya da True y esto no se vuelve a ejecutar. Ver
        # `whatsapp_bot_new_chat_check.is_chat_new_in_waha`.
        is_new_chat = is_chat_new_in_waha(inbound, waha_client)
        store.set_bot_enabled(inbound.chat_id, is_new_chat)
        logger.info(
            "Chat %s visto por primera vez, %s en Waha -> bot_enabled=%s",
            inbound.chat_id,
            "sin historial previo" if is_new_chat else "con historial previo (o falló la consulta)",
            is_new_chat,
        )

    if not store.get_bot_enabled(inbound.chat_id):
        # Activación por chat (opt-in, prendida a mano desde el panel admin, ver
        # ConversationStore.get_bot_enabled/set_bot_enabled) — apagado por default para TODO
        # chat, nuevo o viejo. Mientras esté apagado: silencio total (nada de bienvenida, rate
        # limit, transcripción de audio ni LLM) para que un asesor pueda seguir atendiendo ese
        # chat a mano por WhatsApp Web sin que el bot interfiera. El mensaje entrante SÍ se
        # guarda (sin transcribir; para audio/media no soportada un placeholder, ver
        # `_placeholder_for_untranscribed_inbound` — nunca body vacío) —
        # `add_turn` crea la fila de lead si todavía no existe (`_get_or_create` en
        # whatsapp_bot_store.py) — si no se guardara nada, el chat nunca aparecería en
        # `/admin/prospects` (INNER JOIN contra `messages`) y el admin no tendría forma de
        # enterarse de que hay que activarlo. El dedup de arriba ya evita que un reintento de
        # Waha para el mismo message_id vuelva a escribir esto dos veces. Cuando se active, el
        # flujo normal de más abajo sigue guardando cada turno exactamente como antes (esto no
        # lo duplica: mientras está apagado nunca se llega a esa parte del código).
        store.add_turn(
            inbound.chat_id, "user", _placeholder_for_untranscribed_inbound(inbound), inbound.timestamp
        )
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "bot_disabled_for_chat"}

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

    if store.is_rate_limited(inbound.chat_id):
        # No se descarta el mensaje: quien manda varias burbujas seguidas (uso normal de
        # WhatsApp) no debe perder lo que escribió — se guarda en el historial para que el
        # LLM lo vea en el próximo turno, aunque este no se responda individualmente. Sin el
        # catch-up de abajo, ese turno queda sin respuesta para siempre si el cliente no vuelve
        # a escribir — antes pasaba justo eso (visto en producción).
        logger.info("Chat %s rate limited, se guarda el mensaje sin responder todavía", inbound.chat_id)
        store.add_turn(inbound.chat_id, "user", inbound.text, inbound.timestamp)
        _schedule_rate_limit_catchup(
            inbound.chat_id, inbound.session, waha_client, llm_client, crm_client, store, config, public_base_url, link_secret
        )
        return {"ok": True, "chat_id": inbound.chat_id, "skipped": "rate_limited"}
    store.mark_message_received(inbound.chat_id)

    return _generate_and_send_reply(
        inbound.chat_id, inbound.session, inbound.text, waha_client, llm_client, crm_client, store,
        public_base_url, link_secret, user_turn_created_at=inbound.timestamp,
    )


def _generate_and_send_reply(
    chat_id: str,
    session: str,
    text: str,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    store: ConversationStore,
    public_base_url: str | None,
    link_secret: str | None,
    *,
    sender_name: str | None = None,
    persist_user_turn: bool = True,
    history_override: list[dict[str, str]] | None = None,
    user_turn_created_at: float | None = None,
) -> dict[str, Any]:
    """Resuelve el deal, arma el prompt, llama al LLM y manda la respuesta — el resto de `_process`
    después de las validaciones de entrada (dedup, rate limit, bienvenida, etc.), que no aplican
    cuando se dispara una respuesta sin un mensaje entrante nuevo (`reply_after_activation`).

    `history_override` reemplaza a `store.get_history(chat_id)` como contexto para el LLM — lo usa
    `reply_after_activation` para excluir de ahí el mensaje que se está por responder (que ya está
    guardado en `messages`, a diferencia del flujo normal donde el mensaje entrante todavía no se
    guardó para cuando se arma el prompt). `persist_user_turn=False` evita re-guardar ese mismo
    mensaje como un turno nuevo — solo se agrega el turno del `assistant`. `sender_name` es el
    nombre de perfil de WhatsApp (candidato de identidad, ver más abajo) — `reply_after_activation`
    no lo tiene disponible (no hay `InboundMessage` en ese camino) y queda en `None`.

    `user_turn_created_at` es el `timestamp` real de Waha (`InboundMessage.timestamp`) para el
    turno del cliente que se está por guardar — `None` (default `time.time()` en `add_turn`) en
    `reply_after_activation`, que de todas formas no vuelve a guardar ese turno
    (`persist_user_turn=False`, ya se guardó con su timestamp real cuando llegó de verdad).
    """
    deal_id = store.get_deal_id(chat_id)
    if deal_id is not None and not crm_client.deal_exists(deal_id):
        logger.info("Deal cacheado %s (chat %s) ya no existe en el CRM, se resuelve uno nuevo", deal_id, chat_id)
        store.clear_deal_id(chat_id)
        deal_id = None

    deal_id_before_identity_resolution = deal_id
    if deal_id is None:
        deal_id = _create_deal_from_confirmed_identity(chat_id, crm_client, store)

    awaiting_zone_response = False
    if deal_id is not None and store.get_zone_asked(chat_id) and store.get_zone_in_coverage(chat_id) is None:
        if maybe_handle_zone_response(chat_id, text, waha_client, session, store):
            return {"ok": True, "chat_id": chat_id, "skipped": "zone_resolved"}
        awaiting_zone_response = True

    awaiting_acceptance = False
    awaiting_signature = False
    if not awaiting_zone_response and deal_id is not None and store.get_explanation_sent(chat_id):
        if not store.get_authorization_link_sent(chat_id):
            resolved_base_url, resolved_secret = _resolve_authorization_link_config(public_base_url, link_secret)

            if resolved_base_url and resolved_secret and maybe_handle_acceptance(
                chat_id,
                text,
                deal_id,
                crm_client,
                waha_client,
                session,
                resolved_base_url,
                resolved_secret,
                store,
            ):
                return {"ok": True, "chat_id": chat_id, "skipped": "authorization_link_sent"}

            awaiting_acceptance = True
        elif crm_client.get_authorization_status(crm_client.get_deal(deal_id)) != "firmada":
            # El link ya se mandó pero Bitrix todavía no registra la firma — sin esto, una vez
            # `authorization_link_sent` queda en True el prompt vuelve a ser el genérico de
            # siempre, y el LLM puede responder un "sí"/confirmación de la persona como si el
            # proceso ya hubiera avanzado (bug real: el bot contestó "¡Perfecto, gracias!" a un
            # "sí" que no era la firma). Mientras siga pendiente, cada turno se lo recuerda.
            awaiting_signature = True

    confirmed_name, confirmed_phone = store.get_confirmed_identity(chat_id)

    # Sin deal todavía (identidad sin confirmar): se le muestran al LLM
    # candidatos de nombre/teléfono "fáciles de conseguir" (perfil de
    # WhatsApp, número del chat) para que los confirme con la persona en
    # vez de pedirlos de cero — nunca se dan por buenos sin que la persona
    # los confirme en el chat (eso sigue pasando en _apply_confirmed_identity).
    candidate_name: str | None = None
    candidate_phone: str | None = None
    if deal_id is None:
        candidate_name = sender_name
        candidate_phone, _ = _resolve_phone(chat_id, waha_client, session)

    history = history_override if history_override is not None else store.get_history(chat_id)
    system_prompt = _build_system_prompt(
        templates_store.get_template("whatsapp_system_prompt"),
        confirmed_name,
        confirmed_phone,
        candidate_name,
        candidate_phone,
    )
    if awaiting_zone_response:
        system_prompt += _awaiting_zone_note()
    elif awaiting_acceptance:
        system_prompt += _awaiting_acceptance_note()
    elif awaiting_signature:
        system_prompt += _awaiting_signature_note()
    raw_output = llm_client.reply(system_prompt, history, text)
    if raw_output is None:
        logger.error("LLM no devolvió respuesta para %s, no se envía nada", chat_id)
        return {"ok": False, "chat_id": chat_id, "error": "llm_failed"}

    turn = _parse_llm_output(raw_output)

    if deal_id is not None and turn.signed_claim:
        deal = crm_client.get_deal(deal_id)
        if crm_client.get_authorization_status(deal) != "firmada":
            resolved_base_url, resolved_secret = _resolve_authorization_link_config(public_base_url, link_secret)
            if resolved_base_url and resolved_secret:
                clarification = templates_store.get_template("whatsapp_authorization_not_received_yet")
                waha_client.send_text(chat_id, clarification, session=session)
                process_welcome_and_authorization(
                    deal_id, crm_client, waha_client, resolved_base_url, resolved_secret, session=session
                )
                if persist_user_turn:
                    store.add_turn(chat_id, "user", text, user_turn_created_at)
                store.add_turn(chat_id, "assistant", clarification)
                return {"ok": True, "chat_id": chat_id, "skipped": "signed_claim_not_yet_received"}

    sent = waha_client.send_text(chat_id, turn.reply, session=session)
    if sent:
        if persist_user_turn:
            store.add_turn(chat_id, "user", text, user_turn_created_at)
        store.add_turn(chat_id, "assistant", turn.reply)

        deal_id = _apply_confirmed_identity(chat_id, turn, deal_id, crm_client, store)

        if deal_id is not None and turn.listing != PropertyListing():
            crm_client.update_property_listing(deal_id, turn.listing)
        if deal_id is not None and turn.handoff_requested:
            store.set_bot_enabled(chat_id, False)
            crm_client.add_comment(deal_id, "Bot: cliente pidió hablar con un asesor, bot pausado automáticamente.")

        if deal_id_before_identity_resolution is None and deal_id is not None:
            if not maybe_ask_zone(chat_id, session, waha_client, store):
                # Cliente conocido: la pregunta de zona ya se había mandado antes de
                # confirmar identidad (`whatsapp_bot_welcome.py`), así que la respuesta
                # original se perdió respondiendo nombre/teléfono en su lugar. El deal
                # recién se crea acá — hay que volver a pedirla, si no la conversación
                # queda esperando sin que el bot pida nada.
                zone_in_coverage = store.get_zone_in_coverage(chat_id)
                if zone_in_coverage is None:
                    zone_text = templates_store.get_template("whatsapp_ask_zone")
                    if waha_client.send_text(chat_id, zone_text, session=session):
                        store.add_turn(chat_id, "assistant", zone_text)
                elif zone_in_coverage and not maybe_send_explanation(chat_id, session, waha_client, store):
                    # Misma situación, un paso más adelante: la zona ya estaba confirmada y
                    # la explicación ya se había mandado también, así que la afirmación
                    # original a `whatsapp_ask_acceptance` es la que se perdió acá.
                    if store.get_explanation_sent(chat_id) and not store.get_authorization_link_sent(chat_id):
                        resolved_base_url, resolved_secret = _resolve_authorization_link_config(
                            public_base_url, link_secret
                        )
                        if resolved_base_url and resolved_secret:
                            ask_text = templates_store.get_template("whatsapp_ask_acceptance")
                            if waha_client.send_text(chat_id, ask_text, session=session):
                                store.add_turn(chat_id, "assistant", ask_text)

        maybe_handle_delayed_explanation_request(chat_id, turn.explanation_requested, waha_client, session, store)

    return {"ok": sent, "chat_id": chat_id, "reply": turn.reply}


# Margen sobre `RATE_LIMIT_COOLDOWN_SECONDS` antes de reintentar el mensaje atrapado por el rate
# limit — evita competir por el mismo instante en que el cooldown recién termina de expirar.
_RATE_LIMIT_CATCHUP_BUFFER_SECONDS = 1


def _schedule_rate_limit_catchup(
    chat_id: str,
    session: str,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    store: ConversationStore,
    config: BotConfig,
    public_base_url: str | None,
    link_secret: str | None,
) -> None:
    """Programa un reintento, pasado el cooldown, para el mensaje que el rate limit dejó sin responder.

    `threading.Timer` en un thread daemon — no bloquea la respuesta HTTP del webhook actual, y no
    impide que el proceso termine si el hub se reinicia antes de que dispare (se pierde ese
    reintento puntual, sin problema: es el mismo tipo de pérdida aceptada para el dedup de
    mensajes, ver docstring del módulo). Reusa `reply_after_activation` como callback: esa función
    ya hace exactamente lo que hace falta acá — "si el último turno guardado es del cliente,
    respondelo; si no, no hagas nada" — sin importar si la razón de que quedara sin responder fue
    `bot_enabled=False` o el rate limit. Si para cuando dispara el timer ya se respondió (otro
    mensaje salió del cooldown con normalidad, o alguien más contestó a mano), `reply_after_activation`
    ve el último turno como `assistant` y no hace nada — así que aunque una ráfaga de mensajes
    encolados dentro del cooldown programe varios timers, como mucho uno de ellos termina mandando
    algo.
    """
    timer = threading.Timer(
        RATE_LIMIT_COOLDOWN_SECONDS + _RATE_LIMIT_CATCHUP_BUFFER_SECONDS,
        _rate_limit_catchup,
        args=(chat_id, session, waha_client, llm_client, crm_client, store, config, public_base_url, link_secret),
    )
    timer.daemon = True
    timer.start()


def _rate_limit_catchup(
    chat_id: str,
    session: str,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    store: ConversationStore,
    config: BotConfig,
    public_base_url: str | None,
    link_secret: str | None,
) -> None:
    try:
        reply_after_activation(
            chat_id,
            waha_client,
            llm_client,
            crm_client,
            session=session,
            config=config,
            store=store,
            public_base_url=public_base_url,
            link_secret=link_secret,
        )
    except Exception:  # noqa: BLE001 — corre en un thread aparte, sin nadie que capture la excepción
        logger.exception("Fallo el catch-up de rate limit para %s", chat_id)


def reply_after_activation(
    chat_id: str,
    waha_client: WahaClient,
    llm_client: LlmClient,
    crm_client: CrmClient,
    *,
    session: str = "default",
    config: BotConfig | None = None,
    store: ConversationStore | None = None,
    public_base_url: str | None = None,
    link_secret: str | None = None,
) -> dict[str, Any] | None:
    """Responde de una vez el último mensaje del cliente que quedó pendiente, justo al activar el bot.

    Se llama desde la ruta de admin (`post_activate_bot`) DESPUÉS de `set_bot_enabled(chat_id, True)`
    — mientras el chat estaba apagado, `_process` ya guardaba cada mensaje entrante tal cual llegaba
    (ver docstring del módulo) pero nunca lo respondía; sin esto, el cliente se queda sin respuesta
    hasta que manda un mensaje nuevo después de la activación, aunque el admin ya haya prendido el
    bot mirando ese mismo mensaje pendiente.

    Solo responde si el último turno guardado es del cliente (`role="user"`) — si ya es del
    `assistant` (alguien ya contestó, a mano o el propio bot) o no hay historial todavía, no hay
    nada pendiente y no se manda nada (`None`). El texto del turno pendiente ya está en `messages`
    desde que llegó, así que se pasa como contexto vía `history_override` (excluyéndolo del
    historial que ve el LLM, igual que en el flujo normal donde el mensaje entrante todavía no
    está guardado) y `persist_user_turn=False` evita duplicarlo.

    Además de `config.enabled` (switch global), respeta `store.get_bot_enabled(chat_id)` (switch
    por chat) — sin esto, el catch-up de rate limit (`_rate_limit_catchup`, que también llama a
    esta función) podía mandar una respuesta igual si un admin desactivaba el chat en la ventana
    entre que se programó el timer y que disparó.

    Un turno pendiente vacío o con un placeholder de `_placeholder_for_untranscribed_inbound`
    (nota de voz/media no soportada recibida mientras el chat estaba apagado — no se transcribe
    en ese estado, ver `_process`) tampoco se responde: no hay nada real que contestar.
    """
    store = store or conversation_store
    config = config or load_bot_config()
    if not config.enabled:
        return None

    with store.chat_lock(chat_id):
        if not store.get_bot_enabled(chat_id):
            return None
        history = store.get_history(chat_id)
        if not history or history[-1]["role"] != "user":
            return None
        pending_text = history[-1]["content"]
        if not pending_text.strip() or pending_text in _UNANSWERABLE_PLACEHOLDERS:
            return None

        return _generate_and_send_reply(
            chat_id,
            session,
            pending_text,
            waha_client,
            llm_client,
            crm_client,
            store,
            public_base_url,
            link_secret,
            persist_user_turn=False,
            history_override=history[:-1],
        )


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
