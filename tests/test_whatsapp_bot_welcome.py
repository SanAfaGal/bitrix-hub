from __future__ import annotations

from app.flows.whatsapp_bot import ConversationStore
from app.flows.whatsapp_bot_welcome import maybe_send_first_contact_welcome
from app.message_templates import store as templates_store
from tests.fakes import FakeCrmClient


class FakeWahaClient:
    def __init__(self, send_result: bool = True) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []
        self.voice_calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.send_result

    def send_voice(self, chat_id: str, audio_base64: str, *, session: str | None = None, **_: object) -> bool:
        self.voice_calls.append((chat_id, audio_base64, session))
        return True

    def resolve_lid_to_phone(self, lid: str, session: str | None = None) -> str | None:
        return None


def test_sends_unknown_welcome_when_bitrix_has_no_contact_for_phone() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    handled = maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert handled is True
    assert len(waha.calls) == 1
    chat_id, text, session = waha.calls[0]
    assert chat_id == "573001112233@c.us"
    assert session == "default"
    assert text == templates_store.DEFAULT_TEMPLATES["whatsapp_welcome_unknown"]
    assert store.get_history("573001112233@c.us") == [{"role": "assistant", "content": text}]


def test_sends_known_welcome_with_name_then_offers_explanation_when_bitrix_has_contact_for_phone() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(contacts={"7": {"NAME": "Juan", "LAST_NAME": "Pérez"}})
    crm.contact_by_phone["573001112233"] = "7"
    store = ConversationStore()

    handled = maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert handled is True
    assert [c[1] for c in waha.calls] == [
        templates_store.render_template("whatsapp_welcome_known", nombre="Juan Pérez"),
        templates_store.DEFAULT_TEMPLATES["whatsapp_offer_explanation"],
    ]
    assert waha.voice_calls == []  # el audio ya no se manda sin que la persona confirme
    assert store.get_explanation_offered("573001112233@c.us") is True


def test_does_not_offer_explanation_for_unknown_client() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient()
    store = ConversationStore()

    maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert len(waha.calls) == 1  # solo la bienvenida a cliente nuevo, sin oferta todavía
    assert store.get_explanation_offered("573001112233@c.us") is False


def test_does_not_offer_explanation_when_welcome_text_fails() -> None:
    waha = FakeWahaClient(send_result=False)
    crm = FakeCrmClient(contacts={"7": {"NAME": "Juan", "LAST_NAME": "Pérez"}})
    crm.contact_by_phone["573001112233"] = "7"
    store = ConversationStore()

    maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert len(waha.calls) == 1
    assert store.get_explanation_offered("573001112233@c.us") is False


def test_does_not_send_when_chat_already_has_history() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola")

    handled = maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert handled is False
    assert waha.calls == []


def test_does_not_send_when_chat_already_has_a_deal() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    store.set_deal_id("573001112233@c.us", "6000")

    handled = maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert handled is False
    assert waha.calls == []


def test_does_not_add_turn_when_send_fails() -> None:
    waha = FakeWahaClient(send_result=False)
    crm = FakeCrmClient()
    store = ConversationStore()

    handled = maybe_send_first_contact_welcome("573001112233@c.us", "default", waha, crm, store)

    assert handled is True
    assert store.get_history("573001112233@c.us") == []
