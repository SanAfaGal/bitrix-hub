from __future__ import annotations

from app.waha.outbound_throttle import has_contact_replied, should_throttle_proactive_send


class FakeWahaClient:
    def __init__(self, messages: list[dict] | None) -> None:
        self._messages = messages

    def get_chat_messages(self, chat_id: str, *, limit: int = 50, session: str | None = None) -> list[dict] | None:
        return self._messages


def test_has_contact_replied_true_when_history_has_incoming_message() -> None:
    client = FakeWahaClient(
        [
            {"id": "1", "fromMe": True, "body": "hola"},
            {"id": "2", "fromMe": False, "body": "hola, gracias"},
        ]
    )
    assert has_contact_replied("573001112233@c.us", client) is True


def test_has_contact_replied_false_when_only_hub_messages() -> None:
    client = FakeWahaClient([{"id": "1", "fromMe": True, "body": "hola"}])
    assert has_contact_replied("573001112233@c.us", client) is False


def test_has_contact_replied_ignores_empty_body_incoming_messages() -> None:
    client = FakeWahaClient([{"id": "1", "fromMe": False, "body": ""}])
    assert has_contact_replied("573001112233@c.us", client) is False


def test_has_contact_replied_fails_closed_when_waha_query_fails() -> None:
    client = FakeWahaClient(None)
    assert has_contact_replied("573001112233@c.us", client) is False


def test_should_throttle_proactive_send_never_throttles_once_contact_replied() -> None:
    client = FakeWahaClient([{"id": "1", "fromMe": False, "body": "hola"}])
    for _ in range(10):
        assert should_throttle_proactive_send("573001112233@c.us", client) is False


def test_should_throttle_proactive_send_blocks_after_cap_when_no_reply_yet() -> None:
    client = FakeWahaClient([])
    chat_id = "573001112233@c.us"

    results = [should_throttle_proactive_send(chat_id, client) for _ in range(5)]

    assert results == [False, False, False, False, True]


def test_should_throttle_proactive_send_tracks_chats_independently() -> None:
    client = FakeWahaClient([])

    for _ in range(4):
        assert should_throttle_proactive_send("573001112233@c.us", client) is False
    assert should_throttle_proactive_send("573001112233@c.us", client) is True
    assert should_throttle_proactive_send("573009998877@c.us", client) is False
