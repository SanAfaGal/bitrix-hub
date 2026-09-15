from __future__ import annotations

import json
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.crm.protocol import PropertyListing
from app.flows.whatsapp_bot import BotConfig, ConversationStore, _parse_llm_output, process
from app.flows.whatsapp_bot_checkpoints import seed_default_checkpoints
from app.flows.whatsapp_bot_history_seed import seed_history_from_waha
from app.flows.whatsapp_bot_models import Base
from app.message_templates import store as templates_store
from app.waha.inbound import InboundMessage
from tests.fakes import FakeCrmClient


def _sqlite_file_engine(db_path: str):
    """Engine SQLite sobre un archivo real — para probar que dos `ConversationStore` apuntando
    al mismo archivo ven los mismos datos (simula sobrevivir a un restart del proceso)."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_default_checkpoints(session)
    return engine


@pytest.fixture(autouse=True)
def _skip_first_contact_welcome(monkeypatch: pytest.MonkeyPatch) -> None:
    """La bienvenida de primer contacto (texto fijo, sin LLM) se prueba aparte en
    test_whatsapp_bot_welcome.py — acá se desactiva para no repetir el setup en cada test
    que ya asume que el turno pasa directo por el LLM."""
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)


# `get_bot_enabled` real (sin parchear) — para restaurarlo en los tests puntuales de más abajo
# que sí quieren probar el comportamiento real (activación por chat, default apagado).
_REAL_GET_BOT_ENABLED = ConversationStore.get_bot_enabled


@pytest.fixture(autouse=True)
def _bot_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Casi todos estos tests fueron escritos antes de la activación por chat (opt-in, default
    apagado — ver ConversationStore.get_bot_enabled/set_bot_enabled) y asumen que el bot
    responde a cualquier chat. Se fuerza `get_bot_enabled` a True acá para no repetir
    `store.set_bot_enabled(chat_id, True)` en cada uno de ellos; el comportamiento real (default
    apagado, activación explícita) se prueba en la sección "Activación del bot por chat" más
    abajo, restaurando `_REAL_GET_BOT_ENABLED` puntualmente en esos tests."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", lambda self, chat_id: True)


class FakeWahaClient:
    def __init__(
        self,
        send_result: bool = True,
        resolved_lids: dict[str, str] | None = None,
        media_bytes: bytes | None = b"audio-bytes",
        chat_messages: list[dict] | None = None,
    ) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []
        self.voice_calls: list[tuple[str, str, str | None]] = []
        self._resolved_lids = resolved_lids or {}
        self.resolve_lid_to_phone_calls: list[tuple[str, str | None]] = []
        self._media_bytes = media_bytes
        self.download_media_calls: list[str] = []
        self._chat_messages = chat_messages
        self.get_chat_messages_calls: list[tuple[str, int, bool | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.send_result

    def send_voice(self, chat_id: str, audio_base64: str, *, session: str | None = None, **_: object) -> bool:
        self.voice_calls.append((chat_id, audio_base64, session))
        return True

    def resolve_lid_to_phone(self, lid: str, session: str | None = None) -> str | None:
        self.resolve_lid_to_phone_calls.append((lid, session))
        return self._resolved_lids.get(lid)

    def download_media(self, media_path: str) -> bytes | None:
        self.download_media_calls.append(media_path)
        return self._media_bytes

    def get_chat_messages(
        self, chat_id: str, *, limit: int = 50, from_me: bool | None = None, session: str | None = None
    ) -> list[dict] | None:
        """Usado por `seed_history_from_waha` y por `is_chat_new_in_waha` — ver la sección de
        activación del bot por chat más abajo. Sin mensajes configurados por default (la
        mayoría de los tests de este archivo no llaman a estas funciones). No trunca por
        `limit` (a diferencia de Waha real) porque ningún test de este archivo depende de eso
        — ver `test_whatsapp_bot_new_chat_check.py` para el caso que sí lo necesita."""
        self.get_chat_messages_calls.append((chat_id, limit, from_me))
        if self._chat_messages is None or from_me is None:
            return self._chat_messages
        return [m for m in self._chat_messages if bool(m.get("fromMe")) == from_me]


class FakeLlmClient:
    def __init__(self, reply_text: str | None = "claro, contame que buscas") -> None:
        self.reply_text = reply_text
        self.calls: list[tuple[str, list[dict], str]] = []

    def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
        self.calls.append((system_prompt, history, user_text))
        return self.reply_text


class FakeTranscriptionClient:
    def __init__(self, transcribed_text: str | None = "texto transcrito") -> None:
        self.transcribed_text = transcribed_text
        self.calls: list[bytes] = []

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str | None:
        self.calls.append(audio_bytes)
        return self.transcribed_text


# Instancia compartida para los tests de mensajes de texto (nunca invocada,
# ya que `_resolve_text` solo transcribe cuando `inbound.is_audio` es True).
_TRANSCRIPTION = FakeTranscriptionClient()


_UNSET = object()


def _inbound(
    message_id: str = "msg1",
    chat_id: str = "573001112233@c.us",
    text: str = "hola",
    is_audio: bool = False,
    audio_media_path: str | None | object = _UNSET,
    is_unsupported: bool = False,
    timestamp: float | None = None,
) -> InboundMessage:
    if audio_media_path is _UNSET:
        audio_media_path = "/api/files/msg1.oga" if is_audio else None
    return InboundMessage(
        chat_id=chat_id,
        text=text,
        message_id=message_id,
        session="default",
        is_audio=is_audio,
        audio_media_path=audio_media_path,
        is_unsupported=is_unsupported,
        timestamp=timestamp,
    )


def _enabled_config() -> BotConfig:
    return BotConfig(enabled=True, max_history_turns=6)


def _plain_reply(text: str) -> str:
    return json.dumps({"reply": text, "fields": {}})


# ── process() ────────────────────────────────────────────────────────────


def test_process_skips_when_bot_disabled() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    config = BotConfig(enabled=False, max_history_turns=6)

    result = process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=config, store=ConversationStore())

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled"}
    assert waha.calls == []
    assert llm.calls == []


def test_process_sends_llm_reply_and_updates_history() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert waha.calls == [("573001112233@c.us", "hola! como te ayudo?", "default")]
    assert store.get_history("573001112233@c.us") == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola! como te ayudo?"},
    ]


def test_process_saves_user_turn_with_waha_timestamp_as_created_at() -> None:
    """Bug real: el turno del cliente se guardaba con `time.time()` al momento de procesar el
    webhook, no con el `timestamp` real que Waha manda en el payload — en el panel admin la
    fecha mostrada no correspondía a cuándo se mandó el mensaje de verdad en WhatsApp."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(
        _inbound(text="hola", timestamp=1700000000), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    history = store.get_full_history("573001112233@c.us")
    assert history[0]["created_at"] == 1700000000


def test_process_saves_message_but_does_not_reply_when_rate_limited() -> None:
    """El mensaje no se descarta: si llega dentro del cooldown, se guarda en el historial (para
    que el LLM lo vea en el próximo turno) aunque no se le responda todavía."""
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.mark_message_received("573001112233@c.us")

    result = process(
        _inbound(message_id="msg2", text="y tambien quiero preguntar algo mas", timestamp=1700000005),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "rate_limited"}
    assert waha.calls == []
    assert llm.calls == []
    assert store.get_history("573001112233@c.us") == [
        {"role": "user", "content": "y tambien quiero preguntar algo mas"},
    ]
    assert store.get_full_history("573001112233@c.us")[0]["created_at"] == 1700000005


def test_process_transcribes_audio_and_replies_as_if_it_were_text() -> None:
    waha = FakeWahaClient(media_bytes=b"nota-de-voz")
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    transcription = FakeTranscriptionClient(transcribed_text="hola quiero vender mi apartamento")
    store = ConversationStore()

    result = process(
        _inbound(text="", is_audio=True), waha, llm, crm, transcription, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert waha.download_media_calls == ["/api/files/msg1.oga"]
    assert transcription.calls == [b"nota-de-voz"]
    assert llm.calls[0][2] == "hola quiero vender mi apartamento"
    assert store.get_history("573001112233@c.us") == [
        {"role": "user", "content": "hola quiero vender mi apartamento"},
        {"role": "assistant", "content": "hola! como te ayudo?"},
    ]


def test_process_replies_with_fallback_when_media_download_fails() -> None:
    waha = FakeWahaClient(media_bytes=None)
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    transcription = FakeTranscriptionClient()
    store = ConversationStore()

    result = process(
        _inbound(text="", is_audio=True), waha, llm, crm, transcription, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "transcription_failed"}
    assert transcription.calls == []
    assert llm.calls == []
    assert waha.calls == [
        ("573001112233@c.us", "No pude escuchar tu audio, ¿me lo puedes escribir? 🙏", "default")
    ]


def test_process_replies_with_fallback_when_waha_could_not_download_audio() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    transcription = FakeTranscriptionClient()
    store = ConversationStore()

    result = process(
        _inbound(text="", is_audio=True, audio_media_path=None),
        waha,
        llm,
        crm,
        transcription,
        config=_enabled_config(),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "transcription_failed"}
    assert waha.download_media_calls == []
    assert transcription.calls == []


def test_process_replies_with_fallback_when_transcription_fails() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    transcription = FakeTranscriptionClient(transcribed_text=None)
    store = ConversationStore()

    result = process(
        _inbound(text="", is_audio=True), waha, llm, crm, transcription, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "transcription_failed"}
    assert llm.calls == []
    assert store.get_history("573001112233@c.us") == []


def test_process_replies_with_fallback_when_media_is_unsupported() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    transcription = FakeTranscriptionClient()
    store = ConversationStore()

    result = process(
        _inbound(text="", is_unsupported=True), waha, llm, crm, transcription, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "unsupported_media"}
    assert llm.calls == []
    assert waha.calls == [
        (
            "573001112233@c.us",
            "Por ahora solo puedo leer texto o notas de voz, ¿me lo puedes escribir? 🙏",
            "default",
        )
    ]


def test_process_passes_existing_history_to_llm() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola")
    store.add_turn("573001112233@c.us", "assistant", "hola! como te ayudo?")

    process(_inbound(message_id="msg2", text="tienen apartamentos?"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    _, history, user_text = llm.calls[0]
    assert history == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola! como te ayudo?"},
    ]
    assert user_text == "tienen apartamentos?"


def test_process_does_not_resend_duplicate_message_id() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("ok"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="msg1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)
    result = process(_inbound(message_id="msg1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result["skipped"] == "duplicate_message"
    assert len(waha.calls) == 1
    assert len(llm.calls) == 1


def test_process_does_not_resend_duplicate_message_id_after_restart(tmp_path) -> None:
    """Simula un reinicio del contenedor `api`: el dedup en memoria de la primera instancia
    se pierde, pero la tabla `whatsapp_messages` en MySQL (acá, el mismo archivo SQLite) lo
    recuerda igual — reproduce el bug real (Waha reenvía un mensaje viejo tras reconectar la
    sesión, el bot no debe volver a generar ni mandar una respuesta)."""
    db_path = str(tmp_path / "whatsapp_bot.db")
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("ok"))
    crm = FakeCrmClient()
    first = ConversationStore(engine=_sqlite_file_engine(db_path))

    process(_inbound(message_id="msg1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=first)

    second = ConversationStore(engine=_sqlite_file_engine(db_path))
    result = process(_inbound(message_id="msg1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=second)

    assert result["skipped"] == "duplicate_message"
    assert len(waha.calls) == 1
    assert len(llm.calls) == 1


def test_process_does_not_send_or_store_when_llm_fails() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=None)
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": False, "chat_id": "573001112233@c.us", "error": "llm_failed"}
    assert waha.calls == []
    assert store.get_history("573001112233@c.us") == []


def test_process_does_not_store_history_when_waha_send_fails() -> None:
    waha = FakeWahaClient(send_result=False)
    llm = FakeLlmClient(reply_text=_plain_reply("respuesta"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": False, "chat_id": "573001112233@c.us", "reply": "respuesta"}
    assert store.get_history("573001112233@c.us") == []


# ── Resolución de deal_id / CRM ──────────────────────────────────────────


def test_process_does_not_create_contact_or_deal_before_identity_confirmed() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(chat_id="573001112233@c.us"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola!"}
    assert crm.contact_by_phone == {}
    assert crm.deal_by_contact == {}
    assert store.get_deal_id("573001112233@c.us") is None


def test_process_still_replies_when_lid_unresolved_and_identity_not_confirmed() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(chat_id="123456789012345@lid"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "123456789012345@lid", "reply": "hola!"}
    assert crm.contact_by_username == {}
    assert store.get_deal_id("123456789012345@lid") is None


def test_process_creates_contact_and_deal_once_name_and_phone_confirmed_same_turn() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="573001112233@c.us"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.contact_by_phone == {"573001112233": "5000"}
    assert crm.deal_by_contact == {"5000": "6000"}
    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert crm.find_or_create_property_seller_contact_calls[-1] == ("573001112233", None, "Juan Pérez", None)


def test_process_waits_for_both_name_and_phone_together_in_the_same_turn() -> None:
    """No hay estado "a medias" persistido: aunque el nombre se haya confirmado en un turno y
    el teléfono en otro, no se crea nada hasta que el LLM reporte los DOS juntos en el mismo
    turno (repitiendo el que ya tenía) — así lo instruye el prompt (`_OUTPUT_FORMAT_INSTRUCTIONS`)."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=json.dumps({"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez"}))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") is None
    assert crm.deal_by_contact == {}

    store._last_message_time["573001112233@c.us"] = 0.0  # evita el rate limit entre turnos del test
    llm.reply_text = json.dumps({"reply": "listo", "fields": {}, "client_phone": "3001112233"})
    process(_inbound(message_id="m2", text="mi numero es ese"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    # El teléfono solo, sin repetir el nombre en el mismo turno, tampoco crea nada.
    assert store.get_deal_id("573001112233@c.us") is None
    assert crm.deal_by_contact == {}

    store._last_message_time["573001112233@c.us"] = 0.0
    llm.reply_text = json.dumps(
        {"reply": "Perfecto, gracias", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
    )
    process(_inbound(message_id="m3", text="si, ese mismo"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert crm.deal_by_contact == {"5000": "6000"}
    assert store.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")


def test_process_does_nothing_without_client_full_name_or_client_phone_in_the_turn() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("entendido"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1", text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") is None
    assert store.get_confirmed_identity("573001112233@c.us") == (None, None)


def test_process_reuses_contact_but_creates_new_deal_when_lid_username_already_linked() -> None:
    # Un contacto ya vinculado al identificador @lid (el bot lo hizo en una
    # conversación anterior) se reusa como contacto — pero el deal siempre se
    # crea nuevo, un contacto puede tener varios deals de consignación a la
    # vez (ver app.crm.protocol.CrmClient.create_property_seller_deal).
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    crm.contact_by_username["123456789012345"] = "5000"
    crm.deal_by_contact["5000"] = "9999"
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_deal_id("123456789012345@lid") is not None
    assert store.get_deal_id("123456789012345@lid") != "9999"
    assert crm.find_or_create_property_seller_contact_calls[-1] == (
        "573001112233",
        "123456789012345",
        "Juan Pérez",
        None,
    )


def test_process_reuses_cached_deal_id_without_hitting_crm_lookup_twice() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)
    process(_inbound(message_id="m2", text="otra vez"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    # Un solo contacto/deal creado, aunque hubo 2 mensajes.
    assert len(crm.contact_by_phone) == 1
    assert len(crm.deal_by_contact) == 1


def test_process_serializes_deal_creation_for_same_chat_to_prevent_duplicates() -> None:
    """Regresión de producción: dos mensajes casi simultáneos del mismo chat crearon dos deals
    en Bitrix (race condition en `create_property_seller_deal`, sin lock). Ver el
    docstring de `ConversationStore.chat_lock`."""
    intervals: list[tuple[float, float]] = []
    intervals_lock = threading.Lock()

    class SlowFakeCrmClient(FakeCrmClient):
        def create_property_seller_deal(self, contact_id: str, title: str | None = None, source: str | None = None) -> str | None:
            start = time.monotonic()
            time.sleep(0.05)
            result = super().create_property_seller_deal(contact_id, title, source)
            with intervals_lock:
                intervals.append((start, time.monotonic()))
            return result

    crm = SlowFakeCrmClient()
    store = ConversationStore()
    store.set_confirmed_identity("573001112233@c.us", "Juan Pérez", "573001112233")

    def run(message_id: str) -> None:
        process(
            _inbound(message_id=message_id),
            FakeWahaClient(),
            FakeLlmClient(reply_text=_plain_reply("ok")),
            crm,
            _TRANSCRIPTION,
            config=_enabled_config(),
            store=store,
        )

    t1 = threading.Thread(target=run, args=("m1",))
    t2 = threading.Thread(target=run, args=("m2",))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # El chat_lock serializa los dos process(): para cuando el segundo hilo
    # entra, el primero ya dejó el deal_id cacheado en el store, así que ni
    # siquiera vuelve a llamar a `create_property_seller_deal` — de
    # ahí que `intervals` tenga un solo registro en vez de dos que se
    # solapan (que es justo el bug que reproducía el race condition).
    assert len(crm.deal_by_contact) == 1
    assert len(intervals) == 1


def test_process_recreates_deal_when_cached_deal_was_deleted_in_bitrix() -> None:
    # Identidad ya confirmada de antes (conversación previa) — el self-heal
    # no debe tener que pedirla de nuevo, solo recrear el deal. Siempre crea
    # uno nuevo (no busca otro deal preexistente del contacto para reusar —
    # ver app.crm.protocol.CrmClient.create_property_seller_deal).
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    crm.contact_by_phone["573001112233"] = "5000"
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "40510")  # deal cacheado que ya no existe
    store.set_confirmed_identity("573001112233@c.us", "Juan Pérez", "573001112233")
    crm.deleted_deals.add("40510")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    # El deal viejo (borrado) no se vuelve a consultar como si existiera; se
    # crea uno nuevo para el contacto y el cache se actualiza.
    new_deal_id = store.get_deal_id("573001112233@c.us")
    assert new_deal_id is not None
    assert new_deal_id != "40510"


# ── Candidatos de identidad (nombre de perfil / teléfono del chat) ──────


def test_process_shows_candidate_name_and_phone_in_system_prompt_before_confirmed() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    inbound = InboundMessage(
        chat_id="573001112233@c.us", text="hola", message_id="msg1", session="default", sender_name="Juan Pérez"
    )

    process(inbound, waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert "Juan Pérez" in system_prompt
    assert "573001112233" in system_prompt


def test_process_shows_candidate_phone_resolved_from_lid_in_system_prompt() -> None:
    waha = FakeWahaClient(resolved_lids={"123456789012345": "573001112233@c.us"})
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert waha.resolve_lid_to_phone_calls == [("123456789012345", "default")]
    system_prompt = llm.calls[0][0]
    assert "573001112233" in system_prompt


def test_process_does_not_resolve_candidate_phone_once_deal_exists() -> None:
    waha = FakeWahaClient(resolved_lids={"123456789012345": "573001112233@c.us"})
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("123456789012345@lid", "6000")
    store.set_confirmed_identity("123456789012345@lid", "Juan Pérez", "573001112233")

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert waha.resolve_lid_to_phone_calls == []


def test_process_does_not_send_property_listing_to_llm_system_prompt() -> None:
    """El inmueble ya no se recolecta por chat, se llena en la Autorización de Corretaje."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("ok"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    crm.property_listings["6000"] = PropertyListing(address="Calle 10 # 20-30")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert "Calle 10 # 20-30" not in system_prompt


def test_process_updates_property_listing_when_llm_extracts_fields() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {
                "reply": "perfecto, algo mas?",
                "fields": {"property_type": "Apartamento"},
            }
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.property_listing_updates == [
        ("6000", PropertyListing(property_type="Apartamento")),
    ]


def test_process_does_not_call_update_property_listing_when_no_fields_extracted() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.property_listing_updates == []


# ── Identidad confirmada (nombre/teléfono pedidos por el bot) ───────────


def test_process_shows_no_confirmado_for_both_fields_before_anything_is_known() -> None:
    """Ya no hay estado "a medias" persistido (ver `set_confirmed_identity`): mientras el LLM
    no tenga nombre Y teléfono confirmados a la vez, el system prompt muestra los dos como sin
    confirmar, sin importar cuántos turnos lleve la conversación."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("ok"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert system_prompt.count("(no confirmado)") == 2  # nombre y teléfono, ninguno confirmado todavía


def test_process_saves_confirmed_full_name_on_existing_contact_without_caching_it_locally() -> None:
    """Con el deal ya creado, una corrección de un solo dato se aplica directo en Bitrix — no
    hace falta que el store la tenga (ver `_apply_confirmed_identity`, solo cachea localmente
    cuando tiene los dos juntos, y acá el deal ya existía de antes)."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez"})
    )
    crm = FakeCrmClient(deals={"6000": {"CONTACT_ID": "5000"}})
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.contact_identity_updates == [("5000", None, "Juan Pérez")]
    assert store.get_confirmed_identity("573001112233@c.us") == (None, None)


def test_process_backfills_phone_on_contact_found_only_by_username() -> None:
    # Contacto ya vinculado por @lid pero sin teléfono; la persona lo
    # confirma en el chat, hay que escribirlo sobre el contacto existente.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "listo", "fields": {}, "client_phone": "300 111 2233"})
    )
    crm = FakeCrmClient(deals={"6000": {"CONTACT_ID": "5000"}})
    store = ConversationStore()
    store.set_deal_id("123456789012345@lid", "6000")

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.contact_identity_updates == [("5000", "573001112233", None)]
    assert store.get_confirmed_identity("123456789012345@lid") == (None, None)


def test_process_creates_contact_using_confirmed_phone_and_name_when_lid_unresolved() -> None:
    # Waha no pudo resolver el @lid a teléfono, así que no había contacto
    # creado todavía — el propio cliente confirma teléfono y nombre en el chat.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "listo", "fields": {}, "client_phone": "3001112233"})
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid", message_id="m1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_deal_id("123456789012345@lid") is None  # falta el nombre

    store._last_message_time["123456789012345@lid"] = 0.0  # evita el rate limit entre los 2 turnos del test
    llm.reply_text = json.dumps(
        {"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
    )
    process(
        _inbound(chat_id="123456789012345@lid", message_id="m2", text="Juan Pérez"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
    )

    assert crm.contact_by_phone == {"573001112233": "5000"}
    assert crm.deal_by_contact == {"5000": "6000"}
    assert store.get_deal_id("123456789012345@lid") == "6000"


def test_process_ignores_unparseable_client_phone() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "listo", "fields": {}, "client_phone": "no tengo"})
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_confirmed_identity("123456789012345@lid") == (None, None)
    assert store.get_deal_id("123456789012345@lid") is None


# ── _parse_llm_output ────────────────────────────────────────────────────


def test_parse_llm_output_extracts_reply_and_fields() -> None:
    raw = json.dumps({"reply": "hola", "fields": {"address": "Calle 10", "expected_sale_price": 350000000}})

    turn = _parse_llm_output(raw)

    assert turn.reply == "hola"
    assert turn.listing == PropertyListing(address="Calle 10", expected_sale_price=350000000)
    assert turn.handoff_requested is False


def test_parse_llm_output_ignores_unknown_property_type() -> None:
    raw = json.dumps({"reply": "hola", "fields": {"property_type": "Yate"}})

    turn = _parse_llm_output(raw)

    assert turn.listing.property_type is None


def test_parse_llm_output_ignores_non_numeric_price() -> None:
    raw = json.dumps({"reply": "hola", "fields": {"expected_sale_price": "mucho"}})

    turn = _parse_llm_output(raw)

    assert turn.listing.expected_sale_price is None


def test_parse_llm_output_falls_back_to_plain_text_on_invalid_json() -> None:
    turn = _parse_llm_output("esto no es json")

    assert turn.reply == "esto no es json"
    assert turn.listing == PropertyListing()
    assert turn.handoff_requested is False


def test_parse_llm_output_recovers_json_surrounded_by_extra_text() -> None:
    raw = 'aca esta: {"reply": "hola", "fields": {}} gracias'

    turn = _parse_llm_output(raw)

    assert turn.reply == "hola"
    assert turn.listing == PropertyListing()


def test_parse_llm_output_falls_back_when_reply_key_missing() -> None:
    raw = json.dumps({"fields": {"address": "Calle 10"}})

    turn = _parse_llm_output(raw)

    assert turn.reply == raw
    assert turn.listing == PropertyListing()


def test_parse_llm_output_extracts_handoff_requested() -> None:
    raw = json.dumps({"reply": "la conecto con un asesor", "fields": {}, "handoff_requested": True})

    turn = _parse_llm_output(raw)

    assert turn.handoff_requested is True


def test_parse_llm_output_extracts_client_full_name_and_phone() -> None:
    raw = json.dumps(
        {"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
    )

    turn = _parse_llm_output(raw)

    assert turn.client_full_name == "Juan Pérez"
    assert turn.client_phone == "3001112233"




def test_parse_llm_output_defaults_client_identity_to_none() -> None:
    raw = json.dumps({"reply": "hola", "fields": {}})

    turn = _parse_llm_output(raw)

    assert turn.client_full_name is None
    assert turn.client_phone is None


def test_parse_llm_output_ignores_blank_client_full_name() -> None:
    raw = json.dumps({"reply": "hola", "fields": {}, "client_full_name": "   "})

    turn = _parse_llm_output(raw)

    assert turn.client_full_name is None


# ── AFFIRMATION_RE ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "si", "Sí", "SI", "correcto", "exacto", "así es", "eso es", "confirmo",
        "claro", "claro que si", "está bien", "esta bien.", "de acuerdo",
        "dale", "listo", "vale", "va", "hágale", "hagale", "perfecto",
        "bueno", "ok", "okay", "Sí!", "dale.",
    ],
)
def test_affirmation_re_matches_natural_acceptance_phrases(text: str) -> None:
    from app.flows.whatsapp_bot_llm import AFFIRMATION_RE

    assert AFFIRMATION_RE.match(text.strip())


@pytest.mark.parametrize(
    "text",
    [
        "no sé", "usted es un tonto", "que quieres saber", "a ver", "no", "tal vez",
        # Pedidos como "explícame" caen al LLM a propósito, no a este regex —
        # el LLM ya recibe instrucciones explícitas de marcar
        # "explanation_requested": true ante cualquier forma de pedir la
        # explicación (ver _OUTPUT_FORMAT_INSTRUCTIONS), sin necesidad de
        # mantener una lista de frases hardcodeadas acá.
        "explícame", "cuéntame",
    ],
)
def test_affirmation_re_does_not_match_ambiguous_or_negative_replies(text: str) -> None:
    from app.flows.whatsapp_bot_llm import AFFIRMATION_RE

    assert not AFFIRMATION_RE.match(text.strip())


@pytest.mark.parametrize(
    "text",
    ["no", "No", "no gracias", "ahora no", "despues", "después", "luego", "no quiero", "no es necesario"],
)
def test_negation_re_matches_clear_declines(text: str) -> None:
    from app.flows.whatsapp_bot_llm import NEGATION_RE

    assert NEGATION_RE.match(text.strip())


@pytest.mark.parametrize(
    "text",
    ["si", "claro que si", "no sé", "tal vez", "y esto cuanto dura?"],
)
def test_negation_re_does_not_match_affirmative_or_ambiguous_replies(text: str) -> None:
    from app.flows.whatsapp_bot_llm import NEGATION_RE

    assert not NEGATION_RE.match(text.strip())


def test_parse_llm_output_extracts_signed_claim() -> None:
    from app.flows.whatsapp_bot_llm import _parse_llm_output

    raw = json.dumps({"reply": "listo", "fields": {}, "signed_claim": True})

    turn = _parse_llm_output(raw)

    assert turn.signed_claim is True


def test_parse_llm_output_defaults_signed_claim_to_false() -> None:
    from app.flows.whatsapp_bot_llm import _parse_llm_output

    raw = json.dumps({"reply": "hola", "fields": {}})

    turn = _parse_llm_output(raw)

    assert turn.signed_claim is False


def test_parse_llm_output_extracts_explanation_requested() -> None:
    from app.flows.whatsapp_bot_llm import _parse_llm_output

    raw = json.dumps({"reply": "listo", "fields": {}, "explanation_requested": True})

    turn = _parse_llm_output(raw)

    assert turn.explanation_requested is True


def test_parse_llm_output_defaults_explanation_requested_to_false() -> None:
    from app.flows.whatsapp_bot_llm import _parse_llm_output

    raw = json.dumps({"reply": "hola", "fields": {}})

    turn = _parse_llm_output(raw)

    assert turn.explanation_requested is False


# ── Filtro de números permitidos (WHATSAPP_BOT_ALLOWED_NUMBERS) ─────────


def _config_with_allowed_numbers(*numbers: str) -> BotConfig:
    return BotConfig(enabled=True, max_history_turns=6, allowed_numbers=frozenset(numbers))


def test_process_skips_when_phone_not_in_allowed_numbers() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(chat_id="573009998877@c.us"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_config_with_allowed_numbers("573001112233"),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "573009998877@c.us", "skipped": "number_not_allowed"}
    assert waha.calls == []
    assert llm.calls == []


def test_process_replies_when_phone_in_allowed_numbers() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(chat_id="573001112233@c.us"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_config_with_allowed_numbers("573001112233"),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola!"}


def test_process_resolves_lid_before_checking_allowed_numbers() -> None:
    # Si WhatsApp oculta el número (chat @lid), hay que resolverlo vía Waha
    # antes de filtrar — si no, un número sí permitido queda bloqueado
    # siempre por llegar como @lid en vez de @c.us.
    waha = FakeWahaClient(resolved_lids={"123456789012345": "573001112233@c.us"})
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(chat_id="123456789012345@lid"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_config_with_allowed_numbers("573001112233"),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "123456789012345@lid", "reply": "hola!"}


def test_process_skips_unresolved_lid_when_allowed_numbers_configured() -> None:
    waha = FakeWahaClient()  # Waha no conoce el teléfono detrás del @lid.
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(chat_id="123456789012345@lid"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_config_with_allowed_numbers("573001112233"),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "123456789012345@lid", "skipped": "number_not_allowed"}
    assert llm.calls == []


# ── Cobertura de zona ─────────────────────────────────────────────────

_LINK_SECRET = "test-secret"
_PUBLIC_BASE_URL = "https://hub.example.com"


def test_process_sends_explanation_after_zone_confirmed_by_affirmation() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "zone_coverage")

    result = process(_inbound(text="si"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "zone_resolved"}
    assert store.get_answer("573001112233@c.us", "zone_coverage") is True
    assert store.has_reached("573001112233@c.us", "explanation") is True
    assert llm.calls == []


def test_process_disables_bot_when_zone_declined(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "zone_coverage")
    store.set_bot_enabled("573001112233@c.us", True)

    result = process(_inbound(text="no"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "zone_resolved"}
    assert store.get_answer("573001112233@c.us", "zone_coverage") is False
    assert store.get_bot_enabled("573001112233@c.us") is False
    assert store.has_reached("573001112233@c.us", "explanation") is False
    assert [c[1] for c in waha.calls] == [templates_store.DEFAULT_TEMPLATES["whatsapp_zone_out_of_coverage"]]


def test_process_falls_back_to_llm_with_zone_context_when_reply_is_ambiguous() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("¿tu inmueble está en Medellín o el Oriente antioqueño?"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "zone_coverage")

    result = process(
        _inbound(text="no sé bien la zona"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {
        "ok": True,
        "chat_id": "573001112233@c.us",
        "reply": "¿tu inmueble está en Medellín o el Oriente antioqueño?",
    }
    assert len(llm.calls) == 1
    system_prompt = llm.calls[0][0]
    assert "Medellín o en el Oriente antioqueño" in system_prompt
    assert store.get_answer("573001112233@c.us", "zone_coverage") is None


# ── Explicación del proceso + link de Autorización ──────────────────────


def test_process_asks_zone_right_after_creating_deal_from_confirmed_identity() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(chat_id="573001112233@c.us"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "gracias!"}
    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert store.has_reached("573001112233@c.us", "zone_coverage") is True
    # La explicación (texto + audio + aceptación) todavía no se manda — primero hay que
    # confirmar que el inmueble está en zona de cobertura.
    assert store.has_reached("573001112233@c.us", "explanation") is False
    assert waha.voice_calls == []
    # El "gracias!" del LLM se manda primero, la pregunta de zona después.
    assert waha.calls[0] == ("573001112233@c.us", "gracias!", "default")
    assert waha.calls[1] == ("573001112233@c.us", templates_store.DEFAULT_TEMPLATES["whatsapp_ask_zone"], "default")
    assert len(waha.calls) == 2


def test_process_reasks_acceptance_when_deal_created_after_explanation_already_sent() -> None:
    # Regresión de producción: cliente conocido (`whatsapp_bot_welcome.py` ya confirmó la zona
    # y mandó la explicación + pregunta de aceptación ANTES de que la identidad estuviera
    # confirmada). La afirmación original se perdió respondiendo nombre/teléfono en su lugar;
    # el deal recién se crea en este turno. Como `maybe_send_explanation` no hace nada (ya se
    # había mandado), el bot no debe quedarse callado esperando: debe volver a pedir la
    # aceptación.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.mark_reached("573001112233@c.us", "zone_coverage")
    store.mark_reached("573001112233@c.us", "zone_coverage", value=True)
    store.mark_reached("573001112233@c.us", "explanation")

    result = process(
        _inbound(chat_id="573001112233@c.us"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "gracias!"}
    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert store.has_reached("573001112233@c.us", "authorization_link") is False
    # "gracias!" primero, la re-pregunta de aceptación después — no se queda parado.
    assert waha.calls[0] == ("573001112233@c.us", "gracias!", "default")
    assert len(waha.calls) == 2


def test_process_reasks_zone_question_when_deal_created_after_zone_already_asked() -> None:
    # Análogo al caso de arriba pero un paso antes: `whatsapp_bot_welcome.py` ya mandó la
    # pregunta de zona (cliente conocido por nombre, teléfono todavía sin resolver) ANTES de
    # que la identidad estuviera confirmada. La respuesta original se perdió respondiendo
    # nombre/teléfono en su lugar; el deal recién se crea en este turno. Como `maybe_ask_zone`
    # no hace nada (ya se había preguntado), el bot debe reenviar la pregunta de zona.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.mark_reached("573001112233@c.us", "zone_coverage")

    result = process(
        _inbound(chat_id="573001112233@c.us"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "gracias!"}
    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert store.get_answer("573001112233@c.us", "zone_coverage") is None
    # "gracias!" primero, la re-pregunta de zona después — no se queda parado.
    assert waha.calls[0] == ("573001112233@c.us", "gracias!", "default")
    assert waha.calls[1] == ("573001112233@c.us", templates_store.DEFAULT_TEMPLATES["whatsapp_ask_zone"], "default")
    assert len(waha.calls) == 2


def test_process_does_not_send_explanation_for_deal_that_already_existed_before_this_turn() -> None:
    # Reproduce el caso de un deal cacheado que ya venía de antes (conversación en curso, o
    # cacheado directo en el store como acá) — no debe disparar la explicación de nuevo.
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("todo bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert waha.voice_calls == []
    assert store.has_reached("573001112233@c.us", "explanation") is False


def test_process_sends_authorization_link_when_person_accepts() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient(contacts={"5000": {"PHONE": "3001112233"}})
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "explanation")
    crm._deals["6000"] = {"ID": "6000", "CONTACT_ID": "5000"}

    result = process(
        _inbound(text="si"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "authorization_link_sent"}
    assert crm.authorization_status_updates == [("6000", "pendiente_firma")]
    assert llm.calls == []


def test_process_sends_authorization_link_despite_bitrix_ambiguous_default_status() -> None:
    """Regresión de producción: un deal recién creado en Bitrix ya trae `"pendiente_envio"`
    (default del picklist) en `AUTHORIZATION_STATUS` sin que el link se haya mandado nunca —
    el bot quedaba prometiéndolo sin mandarlo jamás. Ver `maybe_handle_acceptance`."""
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient(contacts={"5000": {"PHONE": "3001112233"}})
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "explanation")
    crm._deals["6000"] = {"ID": "6000", "CONTACT_ID": "5000", "AUTHORIZATION_STATUS": "pendiente_envio"}

    result = process(
        _inbound(text="si"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "authorization_link_sent"}
    assert crm.authorization_status_updates == [("6000", "pendiente_firma")]
    assert store.has_reached("573001112233@c.us", "authorization_link") is True


def test_process_falls_back_to_llm_with_extra_context_when_reply_is_ambiguous() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("claro, no tiene ningún costo. ¿deseas continuar?"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "explanation")

    result = process(
        _inbound(text="esto tiene costo?"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {
        "ok": True,
        "chat_id": "573001112233@c.us",
        "reply": "claro, no tiene ningún costo. ¿deseas continuar?",
    }
    assert len(llm.calls) == 1
    system_prompt = llm.calls[0][0]
    assert "reafirmando la misma pregunta" in system_prompt


def test_process_does_not_resend_explanation_or_reask_once_link_already_sent() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("perfecto, seguimos"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "explanation")
    crm._deals["6000"] = {"ID": "6000", "AUTHORIZATION_STATUS": "pendiente_firma"}

    result = process(
        _inbound(text="si"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "perfecto, seguimos"}
    assert len(llm.calls) == 1


def test_process_reminds_to_sign_when_link_already_sent_but_not_signed_yet() -> None:
    # Regresión de producción: una vez `authorization_link_sent` queda en True, el prompt volvía
    # a ser el genérico de siempre — un "sí" cualquiera de la persona se contestaba como si el
    # proceso ya hubiera avanzado ("¡Perfecto, gracias!") en vez de recordarle que falta firmar.
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("¡Perfecto, gracias!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "explanation")
    store.mark_reached("573001112233@c.us", "authorization_link")
    crm._deals["6000"] = {"ID": "6000", "AUTHORIZATION_STATUS": "pendiente_firma"}

    result = process(
        _inbound(text="si"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "¡Perfecto, gracias!"}
    assert len(llm.calls) == 1
    system_prompt = llm.calls[0][0]
    assert "falta completar y firmar" in system_prompt


def test_process_stops_reminding_to_sign_once_bitrix_says_firmada() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("dale, seguimos"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.mark_reached("573001112233@c.us", "explanation")
    store.mark_reached("573001112233@c.us", "authorization_link")
    crm._deals["6000"] = {"ID": "6000", "AUTHORIZATION_STATUS": "firmada"}

    process(_inbound(text="listo"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert "falta completar y firmar" not in system_prompt


# ── Pedido explícito de explicación antes de que se mande por el camino normal ──


def test_process_sends_audio_when_person_asks_for_it_before_it_was_sent() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "claro, ahora te la mando", "fields": {}, "explanation_requested": True})
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(text="bueno, mándame el audio"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "claro, ahora te la mando"}
    assert len(waha.voice_calls) == 1
    assert waha.calls[-1] == ("573001112233@c.us", templates_store.DEFAULT_TEMPLATES["whatsapp_ask_acceptance"], "default")
    assert store.has_reached("573001112233@c.us", "explanation") is True


def test_process_does_not_resend_explanation_once_already_sent() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("todo bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.mark_reached("573001112233@c.us", "explanation")

    process(_inbound(text="si"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert len(llm.calls) == 1  # ya se mandó el audio antes, este turno sigue el flujo normal
    assert waha.voice_calls == []


# ── Reclamo de firma sin haber firmado en Bitrix ────────────────────────


def test_process_clarifies_and_resends_link_when_person_claims_signed_but_not_in_bitrix() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "listo, ya firmé", "fields": {}, "signed_claim": True})
    )
    crm = FakeCrmClient(
        deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}},
        contacts={"5000": {"PHONE": "3001112233"}},
    )
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    result = process(
        _inbound(text="ya firmé"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "signed_claim_not_yet_received"}
    assert waha.calls[0][1] == templates_store.DEFAULT_TEMPLATES["whatsapp_authorization_not_received_yet"]
    assert crm.authorization_status_updates == [("6000", "pendiente_firma")]


def test_process_does_not_clarify_when_authorization_already_firmada() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "listo, gracias por confirmar", "fields": {}, "signed_claim": True})
    )
    crm = FakeCrmClient(deals={"6000": {"ID": "6000", "AUTHORIZATION_STATUS": "firmada"}})
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    result = process(
        _inbound(text="ya firmé"),
        waha,
        llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
        public_base_url=_PUBLIC_BASE_URL,
        link_secret=_LINK_SECRET,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "listo, gracias por confirmar"}
    assert crm.authorization_status_updates == []


# ── Pausa manual / handoff automático ───────────────────────────────────


def test_process_pauses_bot_and_comments_when_llm_requests_handoff() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "la conecto con un asesor", "fields": {}, "handoff_requested": True})
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.set_bot_enabled("573001112233@c.us", True)

    result = process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "la conecto con un asesor"}
    assert waha.calls == [("573001112233@c.us", "la conecto con un asesor", "default")]
    assert _REAL_GET_BOT_ENABLED(store, "573001112233@c.us") is False
    assert store.get_bot_enabled_reason("573001112233@c.us") == "handoff_requested"
    assert crm.comments == [("6000", "Bot: cliente pidió hablar con un asesor, bot pausado automáticamente.")]


def test_process_does_not_pause_when_handoff_not_requested() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("todo bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.set_bot_enabled("573001112233@c.us", True)

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert _REAL_GET_BOT_ENABLED(store, "573001112233@c.us") is True
    assert crm.comments == []


# ── Activación del bot por chat (opt-in, default apagado) ──────────────


def test_process_skips_when_bot_disabled_for_chat_but_still_saves_the_message(monkeypatch) -> None:
    """`bot_enabled` default False (Task 1) para un chat nuevo: silencio total (nada de
    bienvenida ni LLM), pero el mensaje entrante queda guardado — el admin necesita verlo en
    /admin/prospects para poder activarlo (ver whatsapp_bot_store._list_whatsapp_chats, que
    solo lista leads con al menos un mensaje)."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(text="hola, alguien ahi?", timestamp=1700000010),
        waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store,
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled_for_chat"}
    assert waha.calls == []
    assert llm.calls == []
    assert store.get_history("573001112233@c.us") == [{"role": "user", "content": "hola, alguien ahi?"}]
    assert [c["chat_id"] for c in store.list_chats()] == ["573001112233@c.us"]
    assert store.get_full_history("573001112233@c.us")[0]["created_at"] == 1700000010


def test_process_saves_placeholder_instead_of_empty_body_for_audio_when_bot_disabled(monkeypatch) -> None:
    """Bug real: con el bot apagado, una nota de voz nunca se transcribe (ese código está más
    abajo del return temprano) — `inbound.text` queda `""` y se guardaba tal cual, dejando una
    fila con `content=""` en `messages`."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(text="", is_audio=True), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled_for_chat"}
    assert store.get_history("573001112233@c.us") == [{"role": "user", "content": "[Nota de voz]"}]


def test_process_saves_placeholder_instead_of_empty_body_for_unsupported_media_when_bot_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(text="", is_unsupported=True), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled_for_chat"}
    assert store.get_history("573001112233@c.us") == [{"role": "user", "content": "[Media no soportada]"}]


def test_process_does_not_resend_or_reprocess_when_disabled_chat_gets_retried_message_id(monkeypatch) -> None:
    """El dedup de arriba sigue evitando que un reintento de Waha para el mismo message_id
    vuelva a escribir el mensaje dos veces, incluso con el bot apagado para el chat."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)
    result = process(_inbound(message_id="m1"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "duplicate_message"}
    assert store.get_history("573001112233@c.us") == [{"role": "user", "content": "hola"}]


def test_process_replies_normally_once_bot_enabled_for_chat(monkeypatch) -> None:
    """Con `bot_enabled=True` explícito, sigue el flujo normal (bienvenida/rate-limit/LLM) tal
    cual funcionaba antes de la activación por chat."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_bot_enabled("573001112233@c.us", True)

    result = process(_inbound(text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert waha.calls == [("573001112233@c.us", "hola! como te ayudo?", "default")]


# ── Auto-activación para chats nuevos sin historial en Waha (Tarea 5) ──────


def test_process_auto_activates_bot_for_genuinely_new_chat_with_empty_waha_history(monkeypatch) -> None:
    """Chat nunca visto localmente y Waha no tiene NADA para ese chat_id (lista vacía) — se
    auto-activa (`bot_enabled=True`) sin intervención de un admin y este mismo mensaje ya se
    responde normal (LLM), no queda en `bot_disabled_for_chat`."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(chat_messages=[])
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert store.get_bot_enabled("573001112233@c.us") is True
    assert waha.get_chat_messages_calls == [
        ("573001112233@c.us", 3, True),
        ("573001112233@c.us", 3, False),
    ]


def test_process_auto_activates_bot_when_waha_only_has_the_triggering_message(monkeypatch) -> None:
    """Waha devuelve un solo mensaje y es el mismo que acaba de disparar el webhook (mismo
    `id`) — también cuenta como "sin historial previo", se auto-activa igual que con lista
    vacía."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(
        chat_messages=[{"id": "msg1", "fromMe": False, "body": "hola", "timestamp": 100}]
    )
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(message_id="msg1", text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert store.get_bot_enabled("573001112233@c.us") is True


def test_process_keeps_bot_disabled_for_new_chat_with_prior_waha_history_from_both_sides(monkeypatch) -> None:
    """Waha devuelve mensajes previos de AMBOS lados (cliente y asesor, `fromMe=False`/`True`) —
    ya hay un asesor atendiendo ese chat a mano, se queda apagado (`bot_enabled=False`,
    comportamiento de hoy) para activación manual, y el mensaje entrante se guarda sin
    respuesta."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(
        chat_messages=[
            {"id": "wa_prior_in", "fromMe": False, "body": "hola, ya habia escrito antes", "timestamp": 50},
            {"id": "wa_prior_out", "fromMe": True, "body": "hola! como te ayudo?", "timestamp": 60},
            {"id": "msg1", "fromMe": False, "body": "hola", "timestamp": 100},
        ]
    )
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(message_id="msg1", text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled_for_chat"}
    assert store.get_bot_enabled("573001112233@c.us") is False
    assert llm.calls == []


def test_process_auto_activates_bot_for_unanswered_lead_only_customer_side_ever_wrote(monkeypatch) -> None:
    """Waha devuelve un mensaje previo, pero solo del lado del cliente (`fromMe=False`) — ningún
    asesor le contestó nunca por WhatsApp Web, así que no hay nada humano que el bot vaya a
    interrumpir: se auto-activa igual que un chat genuinamente nuevo."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(
        chat_messages=[
            {"id": "wa_prior_in", "fromMe": False, "body": "hola, nadie me contesto", "timestamp": 50},
            {"id": "msg1", "fromMe": False, "body": "hola", "timestamp": 100},
        ]
    )
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(message_id="msg1", text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert store.get_bot_enabled("573001112233@c.us") is True


def test_process_auto_activates_bot_ignoring_empty_body_e2e_notification_placeholder(monkeypatch) -> None:
    """Waha guarda un mensaje `e2e_notification` (placeholder de intercambio de claves, `body`
    vacío) previo al mensaje real de texto de un chat genuinamente nuevo — no debe contar como
    "historial previo" (bug real: rompía la auto-activación en todo primer contacto por `@lid`,
    ver `whatsapp_bot_new_chat_check.is_chat_new_in_waha`)."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(
        chat_messages=[
            {"id": "placeholder", "fromMe": False, "body": "", "timestamp": 50},
            {"id": "msg1", "fromMe": False, "body": "hola", "timestamp": 100},
        ]
    )
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(message_id="msg1", text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert store.get_bot_enabled("573001112233@c.us") is True


def test_process_fails_closed_and_keeps_bot_disabled_when_waha_history_check_fails(monkeypatch) -> None:
    """Si `get_chat_messages` falla (`None`, ver `FakeWahaClient`/Waha caído) se falla cerrado:
    se trata como si hubiera historial previo, el chat queda apagado — más seguro que arriesgar
    una auto-activación sin poder verificar de verdad que el chat es nuevo."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(chat_messages=None)
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled_for_chat"}
    assert store.get_bot_enabled("573001112233@c.us") is False


def test_process_only_checks_waha_history_once_per_chat_not_on_every_message(monkeypatch) -> None:
    """La consulta a Waha para decidir la auto-activación solo pasa la primera vez que se ve
    un chat_id (creación del lead) — un segundo mensaje del mismo chat, ya con lead local, no
    debe volver a llamar `get_chat_messages` para esto (independiente de `already_processed`,
    que usa otro message_id)."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    waha = FakeWahaClient(chat_messages=[])
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1", text="hola"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)
    process(_inbound(message_id="m2", text="y ahora?"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert waha.get_chat_messages_calls == [
        ("573001112233@c.us", 3, True),
        ("573001112233@c.us", 3, False),
    ]
    assert store.get_bot_enabled("573001112233@c.us") is True


_HISTORY_ANALYSIS_JSON = (
    '{"client_full_name": "Carlos Ramírez", "client_phone": "573001112233", '
    '"process_explained": true, "authorization_mentioned": false, "summary": "resumen"}'
)

_PRIOR_WAHA_MESSAGES = [
    {"id": "wa1", "fromMe": False, "body": "hola, quiero vender mi apto", "timestamp": 100},
    {"id": "wa2", "fromMe": True, "body": "claro, soy Andrea, le explico el proceso", "timestamp": 101},
    {"id": "wa3", "fromMe": False, "body": "listo, gracias", "timestamp": 102},
]


def test_disabled_chat_then_activate_seeds_waha_history_and_next_message_uses_it_as_context(
    monkeypatch,
) -> None:
    """Integración de punta a punta del Hallazgo Crítico de la revisión final: un chat
    desactivado recibe un mensaje entrante (se guarda, sin respuesta); un admin lo activa
    con historial previo real en Waha (`seed_history_from_waha`, mismo mecanismo que usa
    `app/admin/router.py::post_activate_bot`); el próximo mensaje entrante ya debe llegarle
    al LLM con ese historial importado como contexto — no vacío, no solo con el mensaje del
    período desactivado."""
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    crm = FakeCrmClient()

    # 1. Chat desactivado recibe un mensaje entrante — se persiste localmente, sin respuesta.
    inbound_waha = FakeWahaClient()
    inbound_llm = FakeLlmClient()
    result = process(
        _inbound(text="hola, alguien ahi?"),
        inbound_waha,
        inbound_llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
    )
    assert result == {"ok": True, "chat_id": chat_id, "skipped": "bot_disabled_for_chat"}
    assert inbound_waha.calls == []
    assert inbound_llm.calls == []
    assert [m["content"] for m in store.get_full_history(chat_id)] == ["hola, alguien ahi?"]

    # 2. Un admin activa el chat — mismo mecanismo que app/admin/router.py::post_activate_bot:
    # seed_history_from_waha primero, set_bot_enabled después.
    seed_waha = FakeWahaClient(chat_messages=_PRIOR_WAHA_MESSAGES)
    seed_llm = FakeLlmClient(reply_text=_HISTORY_ANALYSIS_JSON)
    seed_result = seed_history_from_waha(store, seed_waha, seed_llm, chat_id)
    store.set_bot_enabled(chat_id, True)

    assert seed_result["seeded"] is True
    assert seed_result["messages_imported"] == 3
    assert len(seed_llm.calls) == 1  # el LLM sí analizó el historial previo, esta vez.

    seeded_history = store.get_full_history(chat_id)
    # El mensaje del período desactivado quedó reemplazado por los 3 turnos reales de
    # Waha (no duplicado — no hay 4 turnos).
    assert [m["content"] for m in seeded_history] == [
        "hola, quiero vender mi apto",
        "claro, soy Andrea, le explico el proceso",
        "listo, gracias",
    ]
    assert store.get_confirmed_identity(chat_id) == ("Carlos Ramírez", "573001112233")
    assert store.has_reached(chat_id, "explanation") is True
    assert store.get_history_seeded(chat_id) is True

    # 3. El próximo mensaje entrante, ya con el bot activado, le llega al LLM con el
    # historial importado como contexto (no vacío).
    reply_waha = FakeWahaClient()
    reply_llm = FakeLlmClient(reply_text=_plain_reply("dale, seguimos con el proceso"))
    result = process(
        _inbound(message_id="msg2", text="ok, sigamos"),
        reply_waha,
        reply_llm,
        crm,
        _TRANSCRIPTION,
        config=_enabled_config(),
        store=store,
    )

    assert result["ok"] is True
    assert len(reply_llm.calls) == 1
    _system_prompt, history_sent_to_llm, user_text = reply_llm.calls[0]
    assert user_text == "ok, sigamos"
    assert history_sent_to_llm  # no vacío: el bot ve la conversación previa importada de Waha.
    assert {"role": "user", "content": "hola, quiero vender mi apto"} in history_sent_to_llm
    assert {"role": "assistant", "content": "claro, soy Andrea, le explico el proceso"} in history_sent_to_llm


# ── Persistencia de historial (sobrevive a un "restart") ────────────────


def test_conversation_store_history_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.add_turn("573001112233@c.us", "user", "hola")
    first.add_turn("573001112233@c.us", "assistant", "hola! como te ayudo?")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_history("573001112233@c.us") == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola! como te ayudo?"},
    ]


def test_conversation_store_dedup_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.mark_processed("msg1")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.already_processed("msg1") is True


def test_conversation_store_deal_id_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_deal_id("573001112233@c.us", "6000")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_deal_id("573001112233@c.us") == "6000"


# ── Identidad confirmada (nombre/teléfono que la persona confirmó al bot) ─


def test_conversation_store_confirmed_identity_defaults_to_none() -> None:
    store = ConversationStore()

    assert store.get_confirmed_identity("573001112233@c.us") == (None, None)


def test_conversation_store_set_confirmed_identity_writes_both_together() -> None:
    store = ConversationStore()

    store.set_confirmed_identity("573001112233@c.us", "Juan Pérez", "573001112233")

    assert store.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")


def test_conversation_store_confirmed_identity_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_confirmed_identity("573001112233@c.us", "Juan Pérez", "573001112233")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")


# ── Explicación del proceso enviada (nombre/teléfono confirmados, deal recién creado) ─


def test_conversation_store_explanation_sent_defaults_to_false() -> None:
    store = ConversationStore()

    assert store.has_reached("573001112233@c.us", "explanation") is False


def test_conversation_store_mark_reached_explanation() -> None:
    store = ConversationStore()

    store.mark_reached("573001112233@c.us", "explanation")

    assert store.has_reached("573001112233@c.us", "explanation") is True


def test_conversation_store_explanation_sent_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_deal_id("573001112233@c.us", "6000")
    first.mark_reached("573001112233@c.us", "explanation")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.has_reached("573001112233@c.us", "explanation") is True


# ── Activación del bot por chat (opt-in, prendido a mano desde el panel admin) ─


def test_conversation_store_bot_enabled_defaults_to_false(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    store = ConversationStore()

    assert store.get_bot_enabled("573001112233@c.us") is False


def test_conversation_store_set_bot_enabled_true() -> None:
    store = ConversationStore()

    store.set_bot_enabled("573001112233@c.us", True)

    assert store.get_bot_enabled("573001112233@c.us") is True


def test_conversation_store_set_bot_enabled_false_again(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", _REAL_GET_BOT_ENABLED)
    store = ConversationStore()

    store.set_bot_enabled("573001112233@c.us", True)
    store.set_bot_enabled("573001112233@c.us", False)

    assert store.get_bot_enabled("573001112233@c.us") is False


def test_conversation_store_bot_enabled_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_bot_enabled("573001112233@c.us", True)

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_bot_enabled("573001112233@c.us") is True


def test_conversation_store_set_bot_enabled_persists_reason() -> None:
    store = ConversationStore()

    store.set_bot_enabled("573001112233@c.us", True, reason="admin_manual")

    assert store.get_bot_enabled_reason("573001112233@c.us") == "admin_manual"


def test_conversation_store_bot_enabled_reason_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_bot_enabled("573001112233@c.us", False, reason="zone_out_of_coverage")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_bot_enabled_reason("573001112233@c.us") == "zone_out_of_coverage"
