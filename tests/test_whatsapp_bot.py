from __future__ import annotations

import json

from app.crm.protocol import PropertyListing
from app.flows.whatsapp_bot import BotConfig, ConversationStore, _parse_llm_output, process
from app.waha.inbound import InboundMessage
from tests.fakes import FakeCrmClient


class FakeWahaClient:
    def __init__(self, send_result: bool = True, resolved_lids: dict[str, str] | None = None) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []
        self._resolved_lids = resolved_lids or {}
        self.resolve_lid_to_phone_calls: list[tuple[str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.send_result

    def resolve_lid_to_phone(self, lid: str, session: str | None = None) -> str | None:
        self.resolve_lid_to_phone_calls.append((lid, session))
        return self._resolved_lids.get(lid)


class FakeLlmClient:
    def __init__(self, reply_text: str | None = "claro, contame que buscas") -> None:
        self.reply_text = reply_text
        self.calls: list[tuple[str, list[dict], str]] = []

    def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
        self.calls.append((system_prompt, history, user_text))
        return self.reply_text


def _inbound(message_id: str = "msg1", chat_id: str = "573001112233@c.us", text: str = "hola") -> InboundMessage:
    return InboundMessage(chat_id=chat_id, text=text, message_id=message_id, session="default")


def _enabled_config() -> BotConfig:
    return BotConfig(enabled=True, max_history_turns=6, system_prompt="system prompt")


def _plain_reply(text: str) -> str:
    return json.dumps({"reply": text, "fields": {}})


# ── process() ────────────────────────────────────────────────────────────


def test_process_skips_when_bot_disabled() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    config = BotConfig(enabled=False, max_history_turns=6, system_prompt="system prompt")

    result = process(_inbound(), waha, llm, crm, config=config, store=ConversationStore())

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled"}
    assert waha.calls == []
    assert llm.calls == []


def test_process_sends_llm_reply_and_updates_history() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola! como te ayudo?"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(text="hola"), waha, llm, crm, config=_enabled_config(), store=store)

    assert result == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert waha.calls == [("573001112233@c.us", "hola! como te ayudo?", "default")]
    assert store.get_history("573001112233@c.us") == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola! como te ayudo?"},
    ]


def test_process_passes_existing_history_to_llm() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("bien"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola")
    store.add_turn("573001112233@c.us", "assistant", "hola! como te ayudo?")

    process(_inbound(message_id="msg2", text="tienen apartamentos?"), waha, llm, crm, config=_enabled_config(), store=store)

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

    process(_inbound(message_id="msg1"), waha, llm, crm, config=_enabled_config(), store=store)
    result = process(_inbound(message_id="msg1"), waha, llm, crm, config=_enabled_config(), store=store)

    assert result["skipped"] == "duplicate_message"
    assert len(waha.calls) == 1
    assert len(llm.calls) == 1


def test_process_does_not_send_or_store_when_llm_fails() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=None)
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    assert result == {"ok": False, "chat_id": "573001112233@c.us", "error": "llm_failed"}
    assert waha.calls == []
    assert store.get_history("573001112233@c.us") == []


def test_process_does_not_store_history_when_waha_send_fails() -> None:
    waha = FakeWahaClient(send_result=False)
    llm = FakeLlmClient(reply_text=_plain_reply("respuesta"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    assert result == {"ok": False, "chat_id": "573001112233@c.us", "reply": "respuesta"}
    assert store.get_history("573001112233@c.us") == []


# ── Resolución de deal_id / CRM ──────────────────────────────────────────


def test_process_creates_contact_and_deal_on_first_message() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="573001112233@c.us"), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.contact_by_phone == {"573001112233": "5000"}
    assert crm.deal_by_contact == {"5000": "6000"}
    assert store.get_deal_id("573001112233@c.us") == "6000"


def test_process_reuses_existing_contact_found_by_lid_username() -> None:
    # Un asesor ya vinculó ese identificador @lid a un contacto real (con
    # teléfono agregado a mano) — el bot debe reusar ese deal, no crear otro.
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    crm.contact_by_username["123456789012345"] = "5000"
    crm.deal_by_contact["5000"] = "6000"
    store = ConversationStore()

    process(
        _inbound(chat_id="123456789012345@lid"),
        waha,
        llm,
        crm,
        config=_enabled_config(),
        store=store,
    )

    assert store.get_deal_id("123456789012345@lid") == "6000"


def test_process_resolves_lid_to_phone_via_waha_and_creates_contact() -> None:
    # Waha ya conoce el teléfono real detrás del @lid (compartió grupo/chat
    # antes) — se debe usar ese teléfono, no quedarse solo con el username.
    waha = FakeWahaClient(resolved_lids={"123456789012345": "573001112233@c.us"})
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(
        _inbound(chat_id="123456789012345@lid"),
        waha,
        llm,
        crm,
        config=_enabled_config(),
        store=store,
    )

    assert waha.resolve_lid_to_phone_calls == [("123456789012345", "default")]
    assert crm.contact_by_phone == {"573001112233": "5000"}
    assert crm.contact_by_username == {"123456789012345": "5000"}
    assert store.get_deal_id("123456789012345@lid") == "6000"


def test_process_still_replies_but_skips_crm_when_lid_has_no_existing_contact() -> None:
    # Sin teléfono no se puede crear el contacto (Bitrix lo exige) — el bot
    # igual debe responder por WhatsApp, solo sin guardar nada en el CRM.
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(
        _inbound(chat_id="123456789012345@lid"),
        waha,
        llm,
        crm,
        config=_enabled_config(),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "123456789012345@lid", "reply": "hola!"}
    assert waha.calls == [("123456789012345@lid", "hola!", "default")]
    assert crm.contact_by_username == {}
    assert store.get_deal_id("123456789012345@lid") is None


def test_process_passes_sender_name_as_display_name_to_crm() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    inbound = InboundMessage(
        chat_id="573001112233@c.us", text="hola", message_id="msg1", session="default", sender_name="Juan Pérez"
    )

    process(inbound, waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.find_or_create_property_seller_contact_calls == [("573001112233", None, "Juan Pérez")]


def test_process_reuses_cached_deal_id_without_hitting_crm_lookup_twice() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1"), waha, llm, crm, config=_enabled_config(), store=store)
    process(_inbound(message_id="m2"), waha, llm, crm, config=_enabled_config(), store=store)

    # Un solo contacto/deal creado, aunque hubo 2 mensajes.
    assert len(crm.contact_by_phone) == 1
    assert len(crm.deal_by_contact) == 1


def test_process_sends_known_fields_to_llm_system_prompt() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("ok"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    crm.property_listings["6000"] = PropertyListing(address="Calle 10 # 20-30")

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert "Calle 10 # 20-30" in system_prompt


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

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.property_listing_updates == [
        ("6000", PropertyListing(property_type="Apartamento", sector_zone_city="El Poblado, Medellín")),
    ]


def test_process_does_not_call_update_property_listing_when_no_fields_extracted() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.property_listing_updates == []


# ── _parse_llm_output ────────────────────────────────────────────────────


def test_parse_llm_output_extracts_reply_and_fields() -> None:
    raw = json.dumps({"reply": "hola", "fields": {"address": "Calle 10", "expected_sale_price": 350000000}})

    reply, listing, handoff = _parse_llm_output(raw)

    assert reply == "hola"
    assert listing == PropertyListing(address="Calle 10", expected_sale_price=350000000)
    assert handoff is False


def test_parse_llm_output_ignores_unknown_property_type() -> None:
    raw = json.dumps({"reply": "hola", "fields": {"property_type": "Yate"}})

    _, listing, _ = _parse_llm_output(raw)

    assert listing.property_type is None


def test_parse_llm_output_ignores_non_numeric_price() -> None:
    raw = json.dumps({"reply": "hola", "fields": {"expected_sale_price": "mucho"}})

    _, listing, _ = _parse_llm_output(raw)

    assert listing.expected_sale_price is None


def test_parse_llm_output_falls_back_to_plain_text_on_invalid_json() -> None:
    reply, listing, handoff = _parse_llm_output("esto no es json")

    assert reply == "esto no es json"
    assert listing == PropertyListing()
    assert handoff is False


def test_parse_llm_output_recovers_json_surrounded_by_extra_text() -> None:
    raw = 'aca esta: {"reply": "hola", "fields": {}} gracias'

    reply, listing, _ = _parse_llm_output(raw)

    assert reply == "hola"
    assert listing == PropertyListing()


def test_parse_llm_output_falls_back_when_reply_key_missing() -> None:
    raw = json.dumps({"fields": {"address": "Calle 10"}})

    reply, listing, _ = _parse_llm_output(raw)

    assert reply == raw
    assert listing == PropertyListing()


def test_parse_llm_output_extracts_handoff_requested() -> None:
    raw = json.dumps({"reply": "la conecto con un asesor", "fields": {}, "handoff_requested": True})

    _, _, handoff = _parse_llm_output(raw)

    assert handoff is True


# ── Filtro de números permitidos (WHATSAPP_BOT_ALLOWED_NUMBERS) ─────────


def _config_with_allowed_numbers(*numbers: str) -> BotConfig:
    return BotConfig(enabled=True, max_history_turns=6, system_prompt="system prompt", allowed_numbers=frozenset(numbers))


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
        config=_config_with_allowed_numbers("573001112233"),
        store=store,
    )

    assert result == {"ok": True, "chat_id": "123456789012345@lid", "skipped": "number_not_allowed"}
    assert llm.calls == []


# ── Pausa manual / handoff automático ───────────────────────────────────


def test_process_skips_when_bot_paused_for_deal() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")
    crm.bot_active["6000"] = False

    result = process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

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

    result = process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

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

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.bot_active_updates == []
    assert crm.comments == []


# ── Persistencia de historial (sobrevive a un "restart") ────────────────


def test_conversation_store_history_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(db_path=db_path)
    first.add_turn("573001112233@c.us", "user", "hola")
    first.add_turn("573001112233@c.us", "assistant", "hola! como te ayudo?")

    second = ConversationStore(db_path=db_path)

    assert second.get_history("573001112233@c.us") == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola! como te ayudo?"},
    ]


def test_conversation_store_deal_id_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(db_path=db_path)
    first.set_deal_id("573001112233@c.us", "6000")

    second = ConversationStore(db_path=db_path)

    assert second.get_deal_id("573001112233@c.us") == "6000"
