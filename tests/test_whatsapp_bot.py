from __future__ import annotations

import json
import threading
import time

import pytest
from sqlalchemy import create_engine

from app.crm.protocol import PropertyListing
from app.flows.whatsapp_bot import BotConfig, ConversationStore, _parse_llm_output, process
from app.flows.whatsapp_bot_models import Base
from app.message_templates import store as templates_store
from app.waha.inbound import InboundMessage
from tests.fakes import FakeCrmClient


def _sqlite_file_engine(db_path: str):
    """Engine SQLite sobre un archivo real — para probar que dos `ConversationStore` apuntando
    al mismo archivo ven los mismos datos (simula sobrevivir a un restart del proceso)."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def _skip_first_contact_welcome(monkeypatch: pytest.MonkeyPatch) -> None:
    """La bienvenida de primer contacto (texto fijo, sin LLM) se prueba aparte en
    test_whatsapp_bot_welcome.py — acá se desactiva para no repetir el setup en cada test
    que ya asume que el turno pasa directo por el LLM."""
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)


class FakeWahaClient:
    def __init__(
        self,
        send_result: bool = True,
        resolved_lids: dict[str, str] | None = None,
        media_bytes: bytes | None = b"audio-bytes",
    ) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []
        self.voice_calls: list[tuple[str, str, str | None]] = []
        self._resolved_lids = resolved_lids or {}
        self.resolve_lid_to_phone_calls: list[tuple[str, str | None]] = []
        self._media_bytes = media_bytes
        self.download_media_calls: list[str] = []

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
    assert crm.find_or_create_property_seller_contact_calls[-1] == ("573001112233", None, "Juan Pérez")


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


def test_process_reuses_contact_already_linked_to_lid_username_when_identity_confirmed() -> None:
    # Un asesor ya vinculó ese identificador @lid a un contacto real en
    # Bitrix (con teléfono agregado a mano) — al confirmarse la identidad
    # por el chat, se debe reusar ese contacto/deal, no crear otro.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    crm.contact_by_username["123456789012345"] = "5000"
    crm.deal_by_contact["5000"] = "6000"
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert store.get_deal_id("123456789012345@lid") == "6000"
    assert crm.find_or_create_property_seller_contact_calls[-1] == ("573001112233", "123456789012345", "Juan Pérez")


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
    en Bitrix (race condition en `find_or_create_property_seller_deal`, sin lock). Ver el
    docstring de `ConversationStore.chat_lock`."""
    intervals: list[tuple[float, float]] = []
    intervals_lock = threading.Lock()

    class SlowFakeCrmClient(FakeCrmClient):
        def find_or_create_property_seller_deal(self, contact_id: str) -> str | None:
            start = time.monotonic()
            time.sleep(0.05)
            result = super().find_or_create_property_seller_deal(contact_id)
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
    # siquiera vuelve a llamar a `find_or_create_property_seller_deal` — de
    # ahí que `intervals` tenga un solo registro en vez de dos que se
    # solapan (que es justo el bug que reproducía el race condition).
    assert len(crm.deal_by_contact) == 1
    assert len(intervals) == 1


def test_process_recreates_deal_when_cached_deal_was_deleted_in_bitrix() -> None:
    # Identidad ya confirmada de antes (conversación previa) — el self-heal
    # no debe tener que pedirla de nuevo, solo recrear el deal.
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    crm.deal_by_contact["5000"] = "6000"
    crm.contact_by_phone["573001112233"] = "5000"
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "40510")  # deal cacheado que ya no existe
    store.set_confirmed_identity("573001112233@c.us", "Juan Pérez", "573001112233")
    crm.deleted_deals.add("40510")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    # El deal viejo (borrado) no se vuelve a consultar como si existiera; se
    # resuelve/crea uno nuevo para el contacto y el cache se actualiza.
    assert store.get_deal_id("573001112233@c.us") == "6000"


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
                "fields": {"property_type": "Apartamento", "sector_zone_city": "El Poblado, Medellín"},
            }
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.property_listing_updates == [
        ("6000", PropertyListing(property_type="Apartamento", sector_zone_city="El Poblado, Medellín")),
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
    ["no sé", "usted es un tonto", "que quieres saber", "a ver", "no", "tal vez"],
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


# ── Explicación del proceso + link de Autorización ──────────────────────

_LINK_SECRET = "test-secret"
_PUBLIC_BASE_URL = "https://hub.example.com"


def test_process_offers_explanation_right_after_creating_deal_from_confirmed_identity() -> None:
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
    assert store.get_explanation_offered("573001112233@c.us") is True
    assert store.get_explanation_sent("573001112233@c.us") is False
    assert waha.voice_calls == []  # el audio no se manda sin que la persona confirme primero
    # El "gracias!" del LLM se manda primero, la explicación (texto+pregunta) después.
    assert waha.calls[0] == ("573001112233@c.us", "gracias!", "default")
    assert len(waha.calls) == 3


def test_process_reasks_acceptance_when_deal_created_after_explanation_already_sent() -> None:
    # Regresión de producción: cliente conocido (`whatsapp_bot_welcome.py` ya ofreció y mandó
    # la explicación + pregunta de aceptación ANTES de que la identidad estuviera confirmada).
    # La afirmación original se perdió respondiendo nombre/teléfono en su lugar; el deal recién
    # se crea en este turno. Como `maybe_send_explanation` no hace nada (ya se había ofrecido),
    # el bot no debe quedarse callado esperando: debe volver a pedir la aceptación.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {"reply": "gracias!", "fields": {}, "client_full_name": "Juan Pérez", "client_phone": "3001112233"}
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_explanation_offered("573001112233@c.us")
    store.set_explanation_sent("573001112233@c.us")

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
    assert store.get_authorization_link_sent("573001112233@c.us") is False
    # "gracias!" primero, la re-pregunta de aceptación después — no se queda parado.
    assert waha.calls[0] == ("573001112233@c.us", "gracias!", "default")
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
    assert store.get_explanation_sent("573001112233@c.us") is False


def test_process_sends_authorization_link_when_person_accepts() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient(contacts={"5000": {"PHONE": "3001112233"}})
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.set_explanation_sent("573001112233@c.us")
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
    store.set_explanation_sent("573001112233@c.us")
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
    assert store.get_authorization_link_sent("573001112233@c.us") is True


def test_process_falls_back_to_llm_with_extra_context_when_reply_is_ambiguous() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("claro, no tiene ningún costo. ¿deseas continuar?"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    store.set_explanation_sent("573001112233@c.us")

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
    store.set_explanation_sent("573001112233@c.us")
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


# ── Oferta de explicación (pregunta antes del audio) ────────────────────


def test_process_sends_audio_and_ask_acceptance_when_person_accepts_explanation_offer() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_explanation_offered("573001112233@c.us")

    result = process(_inbound(text="si"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "explanation_response_handled"}
    assert len(waha.voice_calls) == 1
    assert store.get_explanation_sent("573001112233@c.us") is True
    assert llm.calls == []


def test_process_marks_declined_when_person_declines_explanation_offer() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_explanation_offered("573001112233@c.us")

    result = process(_inbound(text="no gracias"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "explanation_response_handled"}
    assert store.get_explanation_sent("573001112233@c.us") is False
    assert llm.calls == []


def test_process_falls_back_to_llm_without_forcing_a_note_when_offer_reply_is_ambiguous() -> None:
    """Ya no hay una nota especial forzando un sí/no (ver el docstring del gate de
    `maybe_handle_explanation_response` en `_process`) — una respuesta ambigua a la oferta cae
    al turno normal del LLM, que igual ve la oferta en el historial reciente."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("no tiene costo, ¿quieres que te explique?"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_explanation_offered("573001112233@c.us")

    result = process(
        _inbound(text="eso tiene costo?"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {
        "ok": True,
        "chat_id": "573001112233@c.us",
        "reply": "no tiene costo, ¿quieres que te explique?",
    }
    assert len(llm.calls) == 1


def test_process_sends_audio_when_person_asks_for_it_after_having_declined() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "claro, ahora te la mando", "fields": {}, "explanation_requested": True})
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_explanation_offered("573001112233@c.us")

    result = process(
        _inbound(text="bueno, mándame el audio"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store
    )

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "claro, ahora te la mando"}
    assert len(waha.voice_calls) == 1
    assert waha.calls[-1] == ("573001112233@c.us", templates_store.DEFAULT_TEMPLATES["whatsapp_ask_acceptance"], "default")
    assert store.get_explanation_sent("573001112233@c.us") is True


def test_process_does_not_reoffer_explanation_once_already_sent() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("todo bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_explanation_offered("573001112233@c.us")
    store.set_explanation_sent("573001112233@c.us")

    process(_inbound(text="si"), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert len(llm.calls) == 1  # ya se mandó el audio antes, este turno sigue el flujo normal


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


def test_process_skips_when_bot_paused_for_deal() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    crm.bot_active["6000"] = False

    result = process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_paused"}
    assert waha.calls == []
    assert llm.calls == []


def test_process_pauses_bot_and_comments_when_llm_requests_handoff() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "la conecto con un asesor", "fields": {}, "handoff_requested": True})
    )
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    result = process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "la conecto con un asesor"}
    assert waha.calls == [("573001112233@c.us", "la conecto con un asesor", "default")]
    assert crm.bot_active_updates == [("6000", False)]
    assert crm.comments == [("6000", "Bot: cliente pidió hablar con un asesor, bot pausado automáticamente.")]


def test_process_does_not_pause_when_handoff_not_requested() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("todo bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, _TRANSCRIPTION, config=_enabled_config(), store=store)

    assert crm.bot_active_updates == []
    assert crm.comments == []


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

    assert store.get_explanation_sent("573001112233@c.us") is False


def test_conversation_store_set_explanation_sent() -> None:
    store = ConversationStore()

    store.set_explanation_sent("573001112233@c.us")

    assert store.get_explanation_sent("573001112233@c.us") is True


def test_conversation_store_explanation_sent_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_deal_id("573001112233@c.us", "6000")
    first.set_explanation_sent("573001112233@c.us")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_explanation_sent("573001112233@c.us") is True


# ── Oferta de explicación (pregunta antes de mandar el audio) ───────────


def test_conversation_store_explanation_offered_defaults_to_false() -> None:
    store = ConversationStore()

    assert store.get_explanation_offered("573001112233@c.us") is False


def test_conversation_store_set_explanation_offered() -> None:
    store = ConversationStore()

    store.set_explanation_offered("573001112233@c.us")

    assert store.get_explanation_offered("573001112233@c.us") is True


def test_conversation_store_explanation_offered_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(engine=_sqlite_file_engine(db_path))
    first.set_explanation_offered("573001112233@c.us")

    second = ConversationStore(engine=_sqlite_file_engine(db_path))

    assert second.get_explanation_offered("573001112233@c.us") is True
