from __future__ import annotations

import requests

from app.waha.client import WahaClient
from app.waha.settings import WahaSettings


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")


def test_send_text_posts_expected_payload_and_returns_true(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("app.waha.client.requests.post", fake_post)

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola") is True
    assert captured["url"] == "http://localhost:3000/api/sendText"
    assert captured["json"] == {
        "chatId": "573001112233@c.us",
        "text": "hola",
        "session": "default",
    }
    assert captured["headers"] == {"X-Api-Key": "secret"}


def test_send_text_overrides_default_session_when_given(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("app.waha.client.requests.post", fake_post)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.send_text("573001112233@c.us", "hola", session="linea-ventas")

    assert captured["json"]["session"] == "linea-ventas"


def test_send_text_omits_api_key_header_when_not_set(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("app.waha.client.requests.post", fake_post)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.send_text("573001112233@c.us", "hola")

    assert captured["headers"] == {}


def test_send_text_returns_false_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.waha.client.requests.post", fake_post)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola") is False


def test_send_text_returns_false_on_http_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        return FakeResponse(status_code=500)

    monkeypatch.setattr("app.waha.client.requests.post", fake_post)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola") is False


def test_send_text_sequence_sends_each_message_in_order_with_delay_between(monkeypatch) -> None:
    sent_texts = []
    sleeps = []

    monkeypatch.setattr("app.waha.client.requests.post", lambda *a, **k: FakeResponse())
    monkeypatch.setattr("app.waha.client.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr("app.waha.client.random.uniform", lambda lo, hi: 4.2)

    original_send_text = WahaClient.send_text

    def spying_send_text(self, chat_id, text, session=None):
        sent_texts.append(text)
        return original_send_text(self, chat_id, text, session=session)

    monkeypatch.setattr(WahaClient, "send_text", spying_send_text)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    result = client.send_text_sequence("573001112233@c.us", ["hola", "el link"], session="default")

    assert result is True
    assert sent_texts == ["hola", "el link"]
    assert sleeps == [4.2]


def test_send_text_sequence_returns_false_if_any_message_fails(monkeypatch) -> None:
    responses = iter([FakeResponse(), FakeResponse(status_code=500)])
    monkeypatch.setattr("app.waha.client.requests.post", lambda *a, **k: next(responses))
    monkeypatch.setattr("app.waha.client.time.sleep", lambda seconds: None)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    result = client.send_text_sequence("573001112233@c.us", ["hola", "el link"])

    assert result is False


def test_send_text_sequence_does_not_sleep_after_last_message(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr("app.waha.client.requests.post", lambda *a, **k: FakeResponse())
    monkeypatch.setattr("app.waha.client.time.sleep", lambda seconds: sleeps.append(seconds))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    client.send_text_sequence("573001112233@c.us", ["hola"])

    assert sleeps == []
