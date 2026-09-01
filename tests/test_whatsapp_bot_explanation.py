from __future__ import annotations

from app.flows.whatsapp_bot import ConversationStore
from app.flows.whatsapp_bot_explanation import maybe_handle_acceptance, maybe_send_explanation
from app.message_templates import store as templates_store
from tests.fakes import FakeCrmClient

_LINK_SECRET = "test-secret"
_PUBLIC_BASE_URL = "https://hub.example.com"


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


# ── maybe_send_explanation ──────────────────────────────────────────────


def test_sends_explanation_text_voice_and_question_once() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()

    handled = maybe_send_explanation("573001112233@c.us", "default", waha, store)

    assert handled is True
    assert [c[1] for c in waha.calls] == [
        templates_store.DEFAULT_TEMPLATES["whatsapp_process_explanation"],
        templates_store.DEFAULT_TEMPLATES["whatsapp_ask_acceptance"],
    ]
    assert len(waha.voice_calls) == 1
    assert store.get_explanation_sent("573001112233@c.us") is True


def test_does_not_resend_explanation_once_already_sent() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_send_explanation("573001112233@c.us", "default", waha, store)

    assert handled is False
    assert waha.calls == []
    assert waha.voice_calls == []


# ── maybe_handle_acceptance ──────────────────────────────────────────────


def test_sends_authorization_link_when_person_confirms() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(
        deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}},
        contacts={"5000": {"PHONE": "3001112233"}},
    )
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is True
    assert crm.authorization_status_updates == [("6000", "pendiente_firma")]


def test_does_not_handle_when_explanation_not_sent_yet() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}})
    store = ConversationStore()

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is False
    assert crm.authorization_status_updates == []


def test_does_not_handle_when_reply_is_not_a_clear_affirmation() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}})
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us",
        "y esto tiene algun costo?",
        "6000",
        crm,
        waha,
        "default",
        _PUBLIC_BASE_URL,
        _LINK_SECRET,
        store,
    )

    assert handled is False
    assert crm.authorization_status_updates == []


def test_does_not_resend_link_once_authorization_already_pending() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(deals={"6000": {"ID": "6000", "CONTACT_ID": "5000", "AUTHORIZATION_STATUS": "pendiente_firma"}})
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is False
    assert crm.authorization_status_updates == []
