from __future__ import annotations

import requests

from app.bitrix import fields
from app.bitrix.client import BitrixClient


class FakeResponse:
    def __init__(
        self, json_data: dict | None = None, status_code: int = 200, json_error: bool = False, text: str = ""
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.json_error = json_error
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}", response=self)

    def json(self) -> dict:
        if self.json_error:
            raise ValueError("Invalid JSON")
        return self._json_data


def _client() -> BitrixClient:
    return BitrixClient("https://example.bitrix24.com/rest/1/token/")


def test_list_sector_items_returns_items_indexed_by_business_key(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse(
            {
                "result": {
                    "items": [
                        {"id": "10", "title": "El Poblado", fields.FIELD_SECTOR_CODE: "382"},
                        {"id": "11", "title": "Laureles", fields.FIELD_SECTOR_CODE: "0083"},
                    ]
                }
            }
        )

    monkeypatch.setattr("requests.post", fake_post)

    result = _client().list_sector_items()

    assert result == {
        "382": {"id": "10", "title": "El Poblado", fields.FIELD_SECTOR_CODE: "382"},
        "0083": {"id": "11", "title": "Laureles", fields.FIELD_SECTOR_CODE: "0083"},
    }
    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.item.list.json"
    assert captured["json"]["entityTypeId"] == fields.SECTOR_ENTITY_TYPE_ID
    assert captured["json"]["useOriginalUfNames"] == "Y"
    assert captured["json"]["select"] == ["*", "UF_*"]


def test_list_sector_items_follows_pagination(monkeypatch) -> None:
    calls = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append(json.get("start"))
        if json.get("start") in (None, 0):
            return FakeResponse(
                {"result": {"items": [{"id": "1", "title": "A", fields.FIELD_SECTOR_CODE: "1"}]}, "next": 50}
            )
        return FakeResponse({"result": {"items": [{"id": "2", "title": "B", fields.FIELD_SECTOR_CODE: "2"}]}})

    monkeypatch.setattr("requests.post", fake_post)

    result = _client().list_sector_items()

    assert set(result) == {"1", "2"}
    assert calls == [None, 50]


def test_list_sector_items_returns_none_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("requests.post", fake_post)

    assert _client().list_sector_items() is None


def test_list_sector_items_returns_empty_dict_when_no_items(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        return FakeResponse({"result": {"items": []}})

    monkeypatch.setattr("requests.post", fake_post)

    assert _client().list_sector_items() == {}


def test_list_sector_items_skips_items_missing_business_key(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        return FakeResponse(
            {
                "result": {
                    "items": [
                        {"id": "10", "title": "Sin código"},
                        {"id": "11", "title": "Con código", fields.FIELD_SECTOR_CODE: "5"},
                    ]
                }
            }
        )

    monkeypatch.setattr("requests.post", fake_post)

    result = _client().list_sector_items()

    assert list(result) == ["5"]


def test_create_sector_item_returns_new_id(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"result": {"item": {"id": "99"}}})

    monkeypatch.setattr("requests.post", fake_post)

    item_id = _client().create_sector_item({"TITLE": "El Poblado", fields.FIELD_SECTOR_CODE: "382"})

    assert item_id == "99"
    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.item.add.json"
    assert captured["json"]["entityTypeId"] == fields.SECTOR_ENTITY_TYPE_ID
    assert captured["json"]["fields"] == {"TITLE": "El Poblado", fields.FIELD_SECTOR_CODE: "382"}


def test_create_sector_item_returns_none_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("requests.post", fake_post)

    assert _client().create_sector_item({"TITLE": "El Poblado"}) is None


def test_update_sector_item_returns_true_on_success(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse({"result": {"item": {"id": "99"}}})

    monkeypatch.setattr("requests.post", fake_post)

    assert _client().update_sector_item("99", {"TITLE": "Nuevo nombre"}) is True
    assert captured["json"]["id"] == "99"
    assert captured["json"]["fields"] == {"TITLE": "Nuevo nombre"}


def test_update_sector_item_returns_false_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("requests.post", fake_post)

    assert _client().update_sector_item("99", {"TITLE": "Nuevo nombre"}) is False


def test_batch_upsert_sector_items_sends_expected_cmd_and_parses_success(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse(
            {
                "result": {
                    "result": {
                        "create_382": {"item": {"id": "501"}},
                        "update_0083": {"item": {"id": "77"}},
                    },
                    "result_error": {},
                }
            }
        )

    monkeypatch.setattr("requests.post", fake_post)

    result = _client().batch_upsert_sector_items(
        creates={"create_382": {"TITLE": "El Poblado"}},
        updates={"update_0083": ("77", {"TITLE": "Laureles"})},
    )

    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/batch.json"
    assert captured["json"]["halt"] == 0
    assert "create_382" in captured["json"]["cmd"]
    assert captured["json"]["cmd"]["create_382"].startswith("crm.item.add?")
    assert captured["json"]["cmd"]["update_0083"].startswith("crm.item.update?")

    assert result.succeeded_creates == {"create_382": "501"}
    assert result.succeeded_updates == {"update_0083"}
    assert result.failed == {}


def test_batch_upsert_sector_items_chunks_at_fifty(monkeypatch) -> None:
    calls = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append(json["cmd"])
        keys = list(json["cmd"])
        return FakeResponse({"result": {"result": {key: {"item": {"id": key}} for key in keys}, "result_error": {}}})

    monkeypatch.setattr("requests.post", fake_post)

    creates = {f"create_{i}": {"TITLE": f"Sector {i}"} for i in range(60)}

    result = _client().batch_upsert_sector_items(creates=creates, updates={})

    assert len(calls) == 2
    assert len(calls[0]) == 50
    assert len(calls[1]) == 10
    assert len(result.succeeded_creates) == 60


def test_batch_upsert_sector_items_reports_partial_failure(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        return FakeResponse(
            {
                "result": {
                    "result": {"create_382": {"item": {"id": "501"}}},
                    "result_error": {"create_999": {"error": "ERROR_TITLE_REQUIRED"}},
                }
            }
        )

    monkeypatch.setattr("requests.post", fake_post)

    result = _client().batch_upsert_sector_items(
        creates={"create_382": {"TITLE": "El Poblado"}, "create_999": {}},
        updates={},
    )

    assert result.succeeded_creates == {"create_382": "501"}
    assert "create_999" in result.failed


def test_batch_upsert_sector_items_returns_empty_result_without_calling_bitrix(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise AssertionError("no debería llamar a Bitrix si no hay cambios")

    monkeypatch.setattr("requests.post", fake_post)

    result = _client().batch_upsert_sector_items(creates={}, updates={})

    assert result.succeeded_creates == {}
    assert result.succeeded_updates == set()
    assert result.failed == {}
