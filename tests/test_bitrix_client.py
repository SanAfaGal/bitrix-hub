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
    comment_id = client.add_comment("42", "hola")

    assert comment_id == 999
    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.timeline.comment.add.json"
    assert captured["json"]["fields"]["ENTITY_TYPE"] == "deal"


def test_pin_comment_posts_expected_payload(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.pin_comment(999, "42")

    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.timeline.item.pin.json"
    assert captured["json"] == {"id": 999, "ownerTypeId": 2, "ownerId": "42"}


def test_update_deal_does_not_raise_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_deal("42", {"SOME_FIELD": "value"})  # no debe lanzar


def test_get_deal_contact_id_extracts_contact_id() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_deal_contact_id({"ID": "42", "CONTACT_ID": "7"}) == "7"


def test_get_deal_contact_id_returns_none_when_absent() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_deal_contact_id({"ID": "42"}) is None


def test_get_contact_phone_prefers_mobile() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    contact = {
        "PHONE": [
            {"VALUE": "6015551234", "VALUE_TYPE": "WORK"},
            {"VALUE": "3001112233", "VALUE_TYPE": "MOBILE"},
        ]
    }
    assert client.get_contact_phone(contact) == "3001112233"


def test_get_contact_phone_falls_back_to_first_available() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    contact = {"PHONE": [{"VALUE": "6015551234", "VALUE_TYPE": "WORK"}]}
    assert client.get_contact_phone(contact) == "6015551234"


def test_get_contact_phone_returns_none_when_no_phone() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_contact_phone({}) is None
    assert client.get_contact_phone({"PHONE": []}) is None
    assert client.get_contact_phone({"PHONE": [{"VALUE": "", "VALUE_TYPE": "WORK"}]}) is None


def test_get_matricula_extracts_custom_field() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_matricula({"UF_CRM_1773860489786": "5322493"}) == "5322493"


def test_get_matricula_returns_none_when_absent() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.get_matricula({}) is None


def test_upload_file_returns_detail_url(monkeypatch) -> None:
    calls = []

    def fake_post(url: str, timeout: int, data: dict | None = None, files: dict | None = None) -> FakeResponse:
        calls.append({"url": url, "data": data, "files": files})
        if url.endswith("disk.folder.uploadfile.json"):
            return FakeResponse({"result": {"uploadUrl": "https://example.bitrix24.com/upload/?token=abc"}})
        return FakeResponse(
            {
                "result": {
                    "ID": 596274,
                    "NAME": "Autorizacion_42.pdf",
                    "DETAIL_URL": "https://example.bitrix24.com/docs/file/Autorizaciones de corretaje/Autorizacion_42.pdf",
                }
            }
        )

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    result = client.upload_file("595608", "Autorizacion_42.pdf", b"%PDF-1.4 contenido")

    # Los espacios del path (nombres de carpeta) van codificados: si no, Bitrix
    # corta el link al pegarlo como texto plano en un comentario del timeline.
    assert result == "https://example.bitrix24.com/docs/file/Autorizaciones%20de%20corretaje/Autorizacion_42.pdf"
    assert calls[0]["url"] == "https://example.bitrix24.com/rest/1/token/disk.folder.uploadfile.json"
    assert calls[0]["data"] == {"id": "595608", "generateUniqueName": "Y"}
    assert calls[1]["url"] == "https://example.bitrix24.com/upload/?token=abc"
    assert calls[1]["files"] == {"file": ("Autorizacion_42.pdf", b"%PDF-1.4 contenido")}


def test_upload_file_returns_none_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, timeout: int, data: dict | None = None, files: dict | None = None) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.upload_file("595608", "Autorizacion_42.pdf", b"contenido") is None


def test_upload_file_returns_none_when_upload_url_missing(monkeypatch) -> None:
    def fake_post(url: str, timeout: int, data: dict | None = None, files: dict | None = None) -> FakeResponse:
        return FakeResponse({"result": {}})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.upload_file("595608", "Autorizacion_42.pdf", b"contenido") is None


def test_upload_file_returns_none_when_detail_url_missing(monkeypatch) -> None:
    def fake_post(url: str, timeout: int, data: dict | None = None, files: dict | None = None) -> FakeResponse:
        if url.endswith("disk.folder.uploadfile.json"):
            return FakeResponse({"result": {"uploadUrl": "https://example.bitrix24.com/upload/?token=abc"}})
        return FakeResponse({"result": {"ID": 1}})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.upload_file("595608", "Autorizacion_42.pdf", b"contenido") is None


def test_set_welcome_sent_updates_custom_field(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.set_welcome_sent("42")

    assert captured["json"] == {"id": "42", "fields": {"UF_CRM_1776879856695": 1}}


def test_set_duplicado_status_updates_custom_field(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.set_duplicado_status("42", has_duplicate=True)

    assert captured["json"] == {"id": "42", "fields": {"UF_CRM_1773861337167": 89298}}

    client.set_duplicado_status("42", has_duplicate=False)

    assert captured["json"] == {"id": "42", "fields": {"UF_CRM_1773861337167": 89296}}
