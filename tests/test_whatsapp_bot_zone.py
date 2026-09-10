from __future__ import annotations

from app.flows.whatsapp_bot import ConversationStore
from app.flows.whatsapp_bot_zone import maybe_ask_zone, maybe_handle_zone_response
from app.message_templates import store as templates_store


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


# ── maybe_ask_zone ───────────────────────────────────────────────────────


def test_sends_zone_question_and_marks_it_asked() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()

    handled = maybe_ask_zone("573001112233@c.us", "default", waha, store)

    assert handled is True
    assert [c[1] for c in waha.calls] == [templates_store.DEFAULT_TEMPLATES["whatsapp_ask_zone"]]
    assert store.get_zone_asked("573001112233@c.us") is True
    history = store.get_full_history("573001112233@c.us")
    assert [h["role"] for h in history] == ["assistant"]


def test_does_not_reask_zone_once_already_asked() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_zone_asked("573001112233@c.us")

    handled = maybe_ask_zone("573001112233@c.us", "default", waha, store)

    assert handled is False
    assert waha.calls == []


# ── maybe_handle_zone_response ───────────────────────────────────────────


def test_confirms_zone_and_sends_explanation_on_affirmation() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_zone_asked("573001112233@c.us")

    handled = maybe_handle_zone_response("573001112233@c.us", "si", waha, "default", store)

    assert handled is True
    assert store.get_zone_in_coverage("573001112233@c.us") is True
    assert [c[1] for c in waha.calls] == [
        templates_store.DEFAULT_TEMPLATES["whatsapp_process_explanation"],
        templates_store.DEFAULT_TEMPLATES["whatsapp_ask_acceptance"],
    ]
    assert store.get_explanation_sent("573001112233@c.us") is True
    history = store.get_full_history("573001112233@c.us")
    assert history[0] == {"role": "user", "content": "si", "created_at": history[0]["created_at"]}


def test_marks_out_of_coverage_and_disables_bot_on_negation() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_zone_asked("573001112233@c.us")
    store.set_bot_enabled("573001112233@c.us", True)

    handled = maybe_handle_zone_response("573001112233@c.us", "no", waha, "default", store)

    assert handled is True
    assert store.get_zone_in_coverage("573001112233@c.us") is False
    assert [c[1] for c in waha.calls] == [templates_store.DEFAULT_TEMPLATES["whatsapp_zone_out_of_coverage"]]
    assert store.get_bot_enabled("573001112233@c.us") is False
    assert store.get_explanation_sent("573001112233@c.us") is False


def test_does_not_handle_when_reply_is_not_a_clear_yes_or_no() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_zone_asked("573001112233@c.us")

    handled = maybe_handle_zone_response("573001112233@c.us", "no sé bien la dirección exacta", waha, "default", store)

    assert handled is False
    assert waha.calls == []
    assert store.get_zone_in_coverage("573001112233@c.us") is None


def test_does_not_handle_when_zone_was_not_asked_yet() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()

    handled = maybe_handle_zone_response("573001112233@c.us", "si", waha, "default", store)

    assert handled is False
    assert waha.calls == []


def test_does_not_handle_when_zone_already_resolved() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_zone_asked("573001112233@c.us")
    store.set_zone_in_coverage("573001112233@c.us", True)

    handled = maybe_handle_zone_response("573001112233@c.us", "si", waha, "default", store)

    assert handled is False
    assert waha.calls == []
