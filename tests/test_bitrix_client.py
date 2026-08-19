from __future__ import annotations

import requests

from app.bitrix.client import BitrixClient


class FakeResponse:
    def __init__(self, json_data: dict | None = None, status_code: int = 200, json_error: bool = False) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self) -> dict:
        if self.json_error:
            raise ValueError("Invalid JSON")
        return self._json_data


def test_get_deal_returns_result(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        return FakeResponse({"result": {"ID": "42"}})

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    deal = client.get_deal("42")

    assert deal == {"ID": "42"}
    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.deal.get.json"
    assert captured["params"] == {"id": "42"}


def test_get_deal_returns_empty_dict_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_deal("42") == {}


def test_get_contact_returns_result(monkeypatch) -> None:
    captured = {}

    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        return FakeResponse({"result": {"ID": "7", "PHONE": [{"VALUE": "3001112233", "VALUE_TYPE": "MOBILE"}]}})

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    contact = client.get_contact("7")

    assert contact["ID"] == "7"
    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.contact.get.json"
    assert captured["params"] == {"id": "7"}


def test_get_contact_returns_empty_dict_on_request_error(monkeypatch) -> None:
    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_contact("7") == {}


def test_add_comment_posts_expected_payload_and_returns_id(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"result": 999})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    comment_id = client.add_comment("42", "deal", "hola")

    assert comment_id == 999
    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.timeline.comment.add.json"


def test_update_deal_does_not_raise_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_deal("42", {"SOME_FIELD": "value"})  # no debe lanzar
