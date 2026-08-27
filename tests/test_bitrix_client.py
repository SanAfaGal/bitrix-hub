from __future__ import annotations

import requests

from app.bitrix.client import BitrixClient
from app.crm.protocol import PropertyListing


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


def test_deal_exists_returns_true_when_deal_found(monkeypatch) -> None:
    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        return FakeResponse({"result": {"ID": "42"}})

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.deal_exists("42") is True


def test_deal_exists_returns_false_when_bitrix_confirms_not_found(monkeypatch) -> None:
    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        return FakeResponse(
            {"error": "", "error_description": "Not found"}, status_code=400
        )

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.deal_exists("40510") is False


def test_deal_exists_returns_true_on_ambiguous_error(monkeypatch) -> None:
    """Ante error de red/timeout no se puede confirmar que el deal no existe:
    asumir que existe evita recrear deals de más por una falla transitoria."""

    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.deal_exists("42") is True


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


def test_find_or_create_property_seller_contact_returns_existing_match(monkeypatch, caplog) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        assert url.endswith("crm.duplicate.findbycomm.json")
        assert json == {"type": "PHONE", "values": ["573001112233", "+573001112233", "3001112233"]}
        return FakeResponse({"result": {"CONTACT": [7, 9]}})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    with caplog.at_level("INFO"):
        assert client.find_or_create_property_seller_contact("573001112233") == "7"

    assert any("encontrado" in record.message and "id=7" in record.message for record in caplog.records)


def test_find_or_create_property_seller_contact_creates_when_no_match(monkeypatch) -> None:
    calls = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append((url, json))
        if url.endswith("crm.duplicate.findbycomm.json"):
            return FakeResponse({"result": {"CONTACT": []}})
        assert url.endswith("crm.contact.add.json")
        assert json == {
            "fields": {"NAME": "Contacto WhatsApp", "PHONE": [{"VALUE": "+573001112233", "VALUE_TYPE": "MOBILE"}]}
        }
        return FakeResponse({"result": 55})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)
    monkeypatch.setattr(
        "app.bitrix.client.requests.get", lambda url, params, timeout: FakeResponse({"result": {"ID": "55"}})
    )

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact("573001112233") == "55"
    assert len(calls) == 2


def test_find_or_create_property_seller_contact_logs_bitrix_error_body_on_create_failure(monkeypatch, caplog) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        if url.endswith("crm.duplicate.findbycomm.json"):
            return FakeResponse({"result": {"CONTACT": []}})
        return FakeResponse(
            {"error": "ERROR_CORE", "error_description": "Bad field value UF_CRM_1786458989056"},
            status_code=400,
        )

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    with caplog.at_level("ERROR"):
        result = client.find_or_create_property_seller_contact("573001112233")

    assert result is None
    assert any("Bad field value UF_CRM_1786458989056" in record.message for record in caplog.records)


def test_find_or_create_property_seller_contact_returns_none_on_lookup_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact("573001112233") is None


def test_find_or_create_property_seller_contact_returns_none_without_phone_or_username() -> None:
    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact(None) is None


def test_find_or_create_property_seller_contact_falls_back_to_username_lookup(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        assert url.endswith("crm.contact.list.json")
        assert json == {"filter": {"UF_CRM_1786458989056": "123456789012345"}, "select": ["ID"]}
        return FakeResponse({"result": [{"ID": "42"}]})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact(None, "123456789012345") == "42"


def test_find_or_create_property_seller_contact_does_not_create_without_phone(monkeypatch) -> None:
    # Este Bitrix exige "Teléfono" para crear un contacto (crm.contact.add
    # rechaza con 400 sin ese campo) — sin phone, si username no matchea
    # nada, no hay forma correcta de crear el contacto todavía.
    calls = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append((url, json))
        assert url.endswith("crm.contact.list.json")
        return FakeResponse({"result": []})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact(None, "123456789012345") is None
    assert len(calls) == 1  # solo el lookup, nunca intenta crear


def test_find_or_create_property_seller_contact_uses_display_name_when_creating(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        if url.endswith("crm.duplicate.findbycomm.json"):
            return FakeResponse({"result": {"CONTACT": []}})
        assert json["fields"]["NAME"] == "Juan Pérez"
        return FakeResponse({"result": 88})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)
    monkeypatch.setattr(
        "app.bitrix.client.requests.get", lambda url, params, timeout: FakeResponse({"result": {"ID": "88"}})
    )

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact("573001112233", display_name="Juan Pérez") == "88"


def test_find_or_create_property_seller_contact_does_not_create_when_phone_matches_unconverted_lead(
    monkeypatch, caplog
) -> None:
    # Crear un contacto nuevo cuando el teléfono ya tiene un lead sin
    # convertir choca con el control de duplicados de Bitrix (lo borra
    # apenas se crea, aunque después se vincule al lead) — no se crea nada.
    calls = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append((url, json))
        assert url.endswith("crm.duplicate.findbycomm.json")
        return FakeResponse({"result": {"CONTACT": [], "LEAD": [175278]}})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    with caplog.at_level("WARNING"):
        result = client.find_or_create_property_seller_contact("573001112233", display_name="Juan Pérez")

    assert result is None
    assert len(calls) == 1  # solo el lookup, nunca intenta crear
    assert any("lead sin convertir" in record.message and "175278" in record.message for record in caplog.records)


def test_find_or_create_property_seller_contact_returns_none_on_username_lookup_error(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_contact(None, "123456789012345") is None


def test_find_or_create_property_seller_deal_returns_existing_match(monkeypatch, caplog) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        assert url.endswith("crm.deal.list.json")
        assert json["filter"] == {"CONTACT_ID": "7", "CATEGORY_ID": 34}
        return FakeResponse({"result": [{"ID": "123"}]})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    with caplog.at_level("INFO"):
        assert client.find_or_create_property_seller_deal("7") == "123"

    assert any("encontrado" in record.message and "id=123" in record.message for record in caplog.records)


def test_find_or_create_property_seller_deal_creates_when_no_match(monkeypatch) -> None:
    calls = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append((url, json))
        if url.endswith("crm.deal.list.json"):
            return FakeResponse({"result": []})
        assert url.endswith("crm.deal.add.json")
        assert json["fields"]["CONTACT_ID"] == "7"
        assert json["fields"]["CATEGORY_ID"] == 34
        return FakeResponse({"result": 456})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_deal("7") == "456"
    assert len(calls) == 2


def test_find_or_create_property_seller_deal_creates_with_bot_active_checked(monkeypatch) -> None:
    # Gobierno de datos: el checkbox no debe nacer vacío — se marca activo
    # desde la creación en vez de depender del default implícito de
    # BitrixClient.get_bot_active para deals sin el campo seteado.
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        if url.endswith("crm.deal.list.json"):
            return FakeResponse({"result": []})
        assert json["fields"]["UF_CRM_1787762476957"] == 1
        return FakeResponse({"result": 456})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    assert client.find_or_create_property_seller_deal("7") == "456"


def test_get_property_listing_reads_known_fields(monkeypatch) -> None:
    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        return FakeResponse(
            {
                "result": {
                    "UF_CRM_1773860692300": "Calle 10 # 20-30",
                    "UF_CRM_1773861181680": "El Poblado, Medellín",
                    "UF_CRM_1773861238965": "350000000",
                    "UF_CRM_1773860489786": "50C-1945945",
                }
            }
        )

    monkeypatch.setattr("app.bitrix.client.requests.get", fake_get)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    listing = client.get_property_listing("42")

    assert listing.property_type is None  # sin VALUE mapeado todavía
    assert listing.address == "Calle 10 # 20-30"
    assert listing.sector_zone_city == "El Poblado, Medellín"
    assert listing.expected_sale_price == 350000000
    assert listing.registration_number == "50C-1945945"


def test_get_property_listing_returns_all_none_when_deal_empty(monkeypatch) -> None:
    monkeypatch.setattr("app.bitrix.client.requests.get", lambda url, params, timeout: FakeResponse({"result": {}}))

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    listing = client.get_property_listing("42")

    assert listing == PropertyListing()


def test_update_property_listing_only_writes_non_none_fields(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_property_listing(
        "42",
        PropertyListing(address="Calle 10 # 20-30", expected_sale_price=350000000),
    )

    assert captured["json"]["fields"] == {
        "UF_CRM_1773860692300": "Calle 10 # 20-30",
        "UF_CRM_1773861238965": 350000000,
    }


def test_update_property_listing_does_nothing_when_all_none(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise AssertionError("no debería llamar a Bitrix si no hay nada que actualizar")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_property_listing("42", PropertyListing())  # no debe lanzar ni llamar a Bitrix


def test_update_property_listing_skips_property_type_without_value_mapping(monkeypatch, caplog) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    with caplog.at_level("WARNING"):
        client.update_property_listing("42", PropertyListing(property_type="Apartamento"))

    assert any("Apartamento" in record.message for record in caplog.records)
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


def test_update_contact_identity_splits_full_name_into_name_and_last_name(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_contact_identity("42", full_name="Juan Pérez Gómez")

    assert captured["url"] == "https://example.bitrix24.com/rest/1/token/crm.contact.update.json"
    assert captured["json"] == {"id": "42", "fields": {"NAME": "Juan", "LAST_NAME": "Pérez Gómez"}}


def test_update_contact_identity_sets_phone_field(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_contact_identity("42", phone="573001112233")

    assert captured["json"]["fields"] == {"PHONE": [{"VALUE": "573001112233", "VALUE_TYPE": "MOBILE"}]}


def test_update_contact_identity_does_nothing_when_both_none(monkeypatch) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise AssertionError("no debería llamar a Bitrix si no hay nada que actualizar")

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_contact_identity("42")  # no debe lanzar ni llamar a Bitrix


def test_update_contact_identity_single_word_name_sets_only_name(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["json"] = json
        return FakeResponse({"result": True})

    monkeypatch.setattr("app.bitrix.client.requests.post", fake_post)

    client = BitrixClient("https://example.bitrix24.com/rest/1/token/")
    client.update_contact_identity("42", full_name="Juan")

    assert captured["json"]["fields"] == {"NAME": "Juan"}


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
