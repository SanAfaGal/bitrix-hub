from __future__ import annotations

import requests

from app.waha.client import WahaClient
from app.waha.settings import WahaSettings


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self) -> dict:
        return self._json_data or {}


def test_is_reachable_returns_true_when_session_status_is_working(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        assert url == "http://localhost:3000/api/sessions/default"
        return FakeResponse(json_data={"status": "WORKING"})

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.is_reachable() is True


def test_is_reachable_returns_false_when_session_status_is_not_working(monkeypatch) -> None:
    monkeypatch.setattr(
        requests.Session, "get", staticmethod(lambda url, headers, timeout: FakeResponse(json_data={"status": "STOPPED"}))
    )

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.is_reachable() is False


def test_is_reachable_returns_false_when_request_fails(monkeypatch) -> None:
    def _raise(url: str, headers: dict, timeout: int):
        raise requests.exceptions.ConnectionError("no llega")

    monkeypatch.setattr(requests.Session, "get", staticmethod(_raise))

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.is_reachable() is False


def test_get_session_status_returns_full_payload(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        assert url == "http://localhost:3000/api/sessions/default"
        return FakeResponse(json_data={"status": "WORKING", "name": "default", "me": {"pushName": "Ventas"}})

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.get_session_status() == {"status": "WORKING", "name": "default", "me": {"pushName": "Ventas"}}


def test_get_session_status_returns_none_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.get_session_status() is None


def test_start_session_posts_to_start_endpoint_and_returns_true(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.start_session() is True
    assert captured["url"] == "http://localhost:3000/api/sessions/default/start"


def test_start_session_uses_given_session_over_default(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.start_session(session="linea-ventas")

    assert captured["url"] == "http://localhost:3000/api/sessions/linea-ventas/start"


def test_start_session_returns_false_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.start_session() is False


def test_stop_session_posts_to_stop_endpoint_and_returns_true(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.stop_session() is True
    assert captured["url"] == "http://localhost:3000/api/sessions/default/stop"


def test_logout_session_posts_to_logout_endpoint_and_returns_true(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.logout_session() is True
    assert captured["url"] == "http://localhost:3000/api/sessions/default/logout"


def test_logout_session_returns_false_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        requests.Session, "post", staticmethod(lambda url, headers, timeout: FakeResponse(status_code=500))
    )

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.logout_session() is False


def test_get_qr_code_returns_data_url(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse(content=b"fake-png-bytes")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    qr = client.get_qr_code()

    # A diferencia de start/stop/logout/status, el endpoint de QR no lleva el
    # segmento "sessions" — inconsistencia real de la REST API de Waha.
    assert captured["url"] == "http://localhost:3000/api/default/auth/qr"
    assert qr == "data:image/png;base64,ZmFrZS1wbmctYnl0ZXM="


def test_get_qr_code_returns_none_when_session_has_no_qr_to_give(monkeypatch) -> None:
    monkeypatch.setattr(
        requests.Session, "get", staticmethod(lambda url, headers, timeout: FakeResponse(status_code=422))
    )

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.get_qr_code() is None


def test_get_qr_code_returns_none_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.get_qr_code() is None


def test_send_text_posts_expected_payload_and_returns_true(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola", simulate_typing=False) is True
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

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.send_text("573001112233@c.us", "hola", session="linea-ventas", simulate_typing=False)

    assert captured["json"]["session"] == "linea-ventas"


def test_send_text_omits_api_key_header_when_not_set(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.send_text("573001112233@c.us", "hola", simulate_typing=False)

    assert captured["headers"] == {}


def test_send_text_returns_false_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola", simulate_typing=False) is False


def test_send_text_returns_false_on_http_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        return FakeResponse(status_code=500)

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola", simulate_typing=False) is False


def test_send_text_simulates_seen_typing_and_delay_by_default(monkeypatch) -> None:
    posted_urls = []
    sleeps = []

    monkeypatch.setattr(
        requests.Session,
        "post",
        staticmethod(lambda url, json, headers, timeout: posted_urls.append(url) or FakeResponse()),
    )
    monkeypatch.setattr("app.waha.client.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr("app.waha.client.random.uniform", lambda lo, hi: 7.5)

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.send_text("573001112233@c.us", "hola") is True
    assert posted_urls == [
        "http://localhost:3000/api/sendSeen",
        "http://localhost:3000/api/startTyping",
        "http://localhost:3000/api/stopTyping",
        "http://localhost:3000/api/sendText",
    ]
    assert sleeps == [7.5]


def test_mark_seen_start_typing_stop_typing_post_expected_payload(monkeypatch) -> None:
    captured = []

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        captured.append((url, json))
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    assert client.mark_seen("573001112233@c.us") is True
    assert client.start_typing("573001112233@c.us") is True
    assert client.stop_typing("573001112233@c.us") is True
    assert captured == [
        ("http://localhost:3000/api/sendSeen", {"chatId": "573001112233@c.us", "session": "default"}),
        ("http://localhost:3000/api/startTyping", {"chatId": "573001112233@c.us", "session": "default"}),
        ("http://localhost:3000/api/stopTyping", {"chatId": "573001112233@c.us", "session": "default"}),
    ]


def test_mark_seen_returns_false_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "post", staticmethod(fake_post))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.mark_seen("573001112233@c.us") is False


def test_resolve_lid_to_phone_returns_pn_when_mapped(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse(json_data={"lid": "123456789012345@lid", "pn": "573001112233@c.us"})

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.resolve_lid_to_phone("123456789012345") == "573001112233@c.us"
    assert captured["url"] == "http://localhost:3000/api/default/lids/123456789012345"


def test_resolve_lid_to_phone_uses_given_session_over_default(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse(json_data={"pn": None})

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.resolve_lid_to_phone("123456789012345", session="linea-ventas")

    assert captured["url"] == "http://localhost:3000/api/linea-ventas/lids/123456789012345"


def test_resolve_lid_to_phone_returns_none_when_not_mapped_yet(monkeypatch) -> None:
    monkeypatch.setattr(
        requests.Session, "get", staticmethod(lambda url, headers, timeout: FakeResponse(json_data={"pn": None}))
    )

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.resolve_lid_to_phone("123456789012345") is None


def test_resolve_lid_to_phone_returns_none_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.resolve_lid_to_phone("123456789012345") is None


def test_download_media_returns_bytes_on_success(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse(content=b"audio-bytes")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.download_media("/api/files/msg1.oga") == b"audio-bytes"
    assert captured["url"] == "http://localhost:3000/api/files/msg1.oga"


def test_download_media_returns_none_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.download_media("/api/files/msg1.oga") is None


def test_download_media_returns_none_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        requests.Session, "get", staticmethod(lambda url, headers, timeout: FakeResponse(status_code=404))
    )

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.download_media("/api/files/msg1.oga") is None


def test_get_chat_messages_returns_list_with_expected_url_and_params(monkeypatch) -> None:
    captured = {}
    messages = [
        {"id": "1", "fromMe": False, "body": "hola", "timestamp": 100},
        {"id": "2", "fromMe": True, "body": "hola, en qué te ayudo", "timestamp": 101},
    ]

    def fake_get(url: str, params: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(json_data=messages)  # type: ignore[arg-type]

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key="secret", session="default")
    client = WahaClient(settings)

    result = client.get_chat_messages("573001112233@c.us", limit=40)

    assert result == messages
    assert captured["url"] == "http://localhost:3000/api/default/chats/573001112233@c.us/messages"
    assert captured["params"] == {"limit": 40}


def test_get_chat_messages_sends_from_me_filter_when_given(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, params: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["params"] = params
        return FakeResponse(json_data=[])

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    client.get_chat_messages("573001112233@c.us", limit=3, from_me=True)
    assert captured["params"] == {"limit": 3, "filter.fromMe": "true"}

    client.get_chat_messages("573001112233@c.us", limit=3, from_me=False)
    assert captured["params"] == {"limit": 3, "filter.fromMe": "false"}


def test_get_chat_messages_omits_from_me_filter_when_not_given(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, params: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["params"] = params
        return FakeResponse(json_data=[])

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    client.get_chat_messages("573001112233@c.us", limit=3)
    assert captured["params"] == {"limit": 3}


def test_get_chat_messages_uses_given_session_over_default(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, params: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        return FakeResponse(json_data=[])

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)
    client.get_chat_messages("573001112233@c.us", session="linea-ventas")

    assert captured["url"] == "http://localhost:3000/api/linea-ventas/chats/573001112233@c.us/messages"


def test_get_chat_messages_returns_none_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, params: dict, headers: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "get", staticmethod(fake_get))

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.get_chat_messages("573001112233@c.us") is None


def test_get_chat_messages_returns_none_when_response_is_not_a_list(monkeypatch) -> None:
    monkeypatch.setattr(
        requests.Session,
        "get",
        staticmethod(lambda url, params, headers, timeout: FakeResponse(json_data={"error": "x"})),
    )

    settings = WahaSettings(base_url="http://localhost:3000", api_key=None, session="default")
    client = WahaClient(settings)

    assert client.get_chat_messages("573001112233@c.us") is None
