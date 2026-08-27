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


def test_process_does_not_create_contact_or_deal_before_identity_confirmed() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    result = process(_inbound(chat_id="573001112233@c.us"), waha, llm, crm, config=_enabled_config(), store=store)

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

    process(_inbound(chat_id="573001112233@c.us"), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.contact_by_phone == {"573001112233": "5000"}
    assert crm.deal_by_contact == {"5000": "6000"}
    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert crm.find_or_create_property_seller_contact_calls[-1] == ("573001112233", None, "Juan Pérez")


def test_process_waits_for_both_name_and_phone_confirmed_across_turns() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=json.dumps({"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez"}))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1"), waha, llm, crm, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") is None
    assert crm.deal_by_contact == {}

    store._last_message_time["573001112233@c.us"] = 0.0  # evita el rate limit entre los 2 turnos del test
    llm.reply_text = json.dumps({"reply": "listo", "fields": {}, "client_phone": "3001112233"})
    process(_inbound(message_id="m2", text="mi numero es ese"), waha, llm, crm, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert crm.deal_by_contact == {"5000": "6000"}


def test_process_creates_deal_when_person_confirms_proposed_identity_with_plain_si() -> None:
    """Reproduce el bug real: el LLM propone nombre/teléfono para confirmar, la persona
    responde solo "Si" en el siguiente turno y, aunque el LLM no repita esos valores en
    `client_full_name`/`client_phone` de ese turno, el bot debe crear igual el deal."""
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {
                "reply": "Confirma que su nombre es Juan Pérez y su número es 3001112233, ¿es correcto?",
                "fields": {},
                "proposed_full_name": "Juan Pérez",
                "proposed_phone": "3001112233",
            }
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1", text="Juan Pérez\n3001112233"), waha, llm, crm, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") is None

    store._last_message_time["573001112233@c.us"] = 0.0
    llm.reply_text = json.dumps({"reply": "Perfecto, gracias", "fields": {}})
    process(_inbound(message_id="m2", text="Si"), waha, llm, crm, config=_enabled_config(), store=store)

    assert store.get_deal_id("573001112233@c.us") == "6000"
    assert crm.deal_by_contact == {"5000": "6000"}
    assert store.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")


def test_process_does_not_promote_pending_identity_without_affirmative_reply() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps(
            {
                "reply": "Confirma que su nombre es Juan Pérez, ¿es correcto?",
                "fields": {},
                "proposed_full_name": "Juan Pérez",
                "proposed_phone": "3001112233",
            }
        )
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(message_id="m1"), waha, llm, crm, config=_enabled_config(), store=store)

    store._last_message_time["573001112233@c.us"] = 0.0
    llm.reply_text = json.dumps({"reply": "entendido", "fields": {}})
    process(_inbound(message_id="m2", text="No, mi nombre es otro"), waha, llm, crm, config=_enabled_config(), store=store)

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

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, config=_enabled_config(), store=store)

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

    process(_inbound(message_id="m1"), waha, llm, crm, config=_enabled_config(), store=store)
    process(_inbound(message_id="m2", text="otra vez"), waha, llm, crm, config=_enabled_config(), store=store)

    # Un solo contacto/deal creado, aunque hubo 2 mensajes.
    assert len(crm.contact_by_phone) == 1
    assert len(crm.deal_by_contact) == 1


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
    store.set_confirmed_name("573001112233@c.us", "Juan Pérez")
    store.set_confirmed_phone("573001112233@c.us", "573001112233")
    crm.deleted_deals.add("40510")

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

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

    process(inbound, waha, llm, crm, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert "Juan Pérez" in system_prompt
    assert "573001112233" in system_prompt


def test_process_shows_candidate_phone_resolved_from_lid_in_system_prompt() -> None:
    waha = FakeWahaClient(resolved_lids={"123456789012345": "573001112233@c.us"})
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, config=_enabled_config(), store=store)

    assert waha.resolve_lid_to_phone_calls == [("123456789012345", "default")]
    system_prompt = llm.calls[0][0]
    assert "573001112233" in system_prompt


def test_process_does_not_resolve_candidate_phone_once_deal_exists() -> None:
    waha = FakeWahaClient(resolved_lids={"123456789012345": "573001112233@c.us"})
    llm = FakeLlmClient(reply_text=_plain_reply("hola!"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("123456789012345@lid", "6000")
    store.set_confirmed_name("123456789012345@lid", "Juan Pérez")
    store.set_confirmed_phone("123456789012345@lid", "573001112233")

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, config=_enabled_config(), store=store)

    assert waha.resolve_lid_to_phone_calls == []


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


# ── Identidad confirmada (nombre/teléfono pedidos por el bot) ───────────


def test_process_sends_confirmed_identity_block_to_llm_system_prompt() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text=_plain_reply("ok"))
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_confirmed_name("573001112233@c.us", "Juan Pérez")

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    system_prompt = llm.calls[0][0]
    assert "Juan Pérez" in system_prompt
    assert "(no confirmado)" in system_prompt  # teléfono todavía sin confirmar


def test_process_stores_and_saves_confirmed_full_name_on_existing_contact() -> None:
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez"})
    )
    crm = FakeCrmClient(deals={"6000": {"CONTACT_ID": "5000"}})
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    process(_inbound(), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.contact_identity_updates == [("5000", None, "Juan Pérez")]
    assert store.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", None)


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

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, config=_enabled_config(), store=store)

    assert crm.contact_identity_updates == [("5000", "573001112233", None)]
    assert store.get_confirmed_identity("123456789012345@lid") == (None, "573001112233")


def test_process_creates_contact_using_confirmed_phone_and_name_when_lid_unresolved() -> None:
    # Waha no pudo resolver el @lid a teléfono, así que no había contacto
    # creado todavía — el propio cliente confirma teléfono y nombre en el chat.
    waha = FakeWahaClient()
    llm = FakeLlmClient(
        reply_text=json.dumps({"reply": "listo", "fields": {}, "client_phone": "3001112233"})
    )
    crm = FakeCrmClient()
    store = ConversationStore()

    process(_inbound(chat_id="123456789012345@lid", message_id="m1"), waha, llm, crm, config=_enabled_config(), store=store)

    assert store.get_deal_id("123456789012345@lid") is None  # falta el nombre

    store._last_message_time["123456789012345@lid"] = 0.0  # evita el rate limit entre los 2 turnos del test
    llm.reply_text = json.dumps({"reply": "gracias", "fields": {}, "client_full_name": "Juan Pérez"})
    process(
        _inbound(chat_id="123456789012345@lid", message_id="m2", text="Juan Pérez"),
        waha,
        llm,
        crm,
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

    process(_inbound(chat_id="123456789012345@lid"), waha, llm, crm, config=_enabled_config(), store=store)

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


def test_parse_llm_output_extracts_proposed_full_name_and_phone() -> None:
    raw = json.dumps(
        {"reply": "confirma?", "fields": {}, "proposed_full_name": "Juan Pérez", "proposed_phone": "3001112233"}
    )

    turn = _parse_llm_output(raw)

    assert turn.proposed_full_name == "Juan Pérez"
    assert turn.proposed_phone == "3001112233"


def test_parse_llm_output_defaults_client_identity_to_none() -> None:
    raw = json.dumps({"reply": "hola", "fields": {}})

    turn = _parse_llm_output(raw)

    assert turn.client_full_name is None
    assert turn.client_phone is None


def test_parse_llm_output_ignores_blank_client_full_name() -> None:
    raw = json.dumps({"reply": "hola", "fields": {}, "client_full_name": "   "})

    turn = _parse_llm_output(raw)

    assert turn.client_full_name is None


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


# ── Identidad confirmada (nombre/teléfono que la persona confirmó al bot) ─


def test_conversation_store_confirmed_identity_defaults_to_none() -> None:
    store = ConversationStore()

    assert store.get_confirmed_identity("573001112233@c.us") == (None, None)


def test_conversation_store_set_confirmed_name_and_phone_independently() -> None:
    store = ConversationStore()

    store.set_confirmed_name("573001112233@c.us", "Juan Pérez")
    assert store.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", None)

    store.set_confirmed_phone("573001112233@c.us", "573001112233")
    assert store.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")


def test_conversation_store_confirmed_identity_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(db_path=db_path)
    first.set_confirmed_name("573001112233@c.us", "Juan Pérez")
    first.set_confirmed_phone("573001112233@c.us", "573001112233")

    second = ConversationStore(db_path=db_path)

    assert second.get_confirmed_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")


def test_conversation_store_pending_identity_defaults_to_none() -> None:
    store = ConversationStore()

    assert store.get_pending_identity("573001112233@c.us") == (None, None)


def test_conversation_store_set_and_clear_pending_identity() -> None:
    store = ConversationStore()

    store.set_pending_name("573001112233@c.us", "Juan Pérez")
    store.set_pending_phone("573001112233@c.us", "573001112233")

    assert store.get_pending_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")

    store.clear_pending_identity("573001112233@c.us")

    assert store.get_pending_identity("573001112233@c.us") == (None, None)


def test_conversation_store_pending_identity_survives_new_instance_same_db_file(tmp_path) -> None:
    db_path = str(tmp_path / "whatsapp_bot.db")

    first = ConversationStore(db_path=db_path)
    first.set_pending_name("573001112233@c.us", "Juan Pérez")
    first.set_pending_phone("573001112233@c.us", "573001112233")

    second = ConversationStore(db_path=db_path)

    assert second.get_pending_identity("573001112233@c.us") == ("Juan Pérez", "573001112233")
