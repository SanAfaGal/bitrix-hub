from __future__ import annotations

import base64

import cv2
import pymupdf as fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.forms.rate_limit as rate_limit_module
from app.forms.link_token import sign_deal_id
from app.main import app

client = TestClient(app)

_LINK_SECRET = "test-secret"


def _token_for(deal_id: str) -> str:
    return sign_deal_id(deal_id, _LINK_SECRET)


class FakeCrmClient:
    """Fake mínimo para tests del router: deal sin estado de firma por defecto."""

    def __init__(
        self,
        authorization_status: str | None = None,
        upload_file_result: str | None = "https://example.bitrix24.com/docs/file/firmado.pdf",
        contact_id: str | None = "7",
        contact_phone: str | None = "573001112233",
    ) -> None:
        self.authorization_status = authorization_status
        self.comments: list[tuple[str, str]] = []
        self.status_updates: list[tuple[str, str]] = []
        self.uploaded_files: list[tuple[str, str, bytes]] = []
        self.property_listing_updates: list[tuple[str, object]] = []
        self.bot_active_updates: list[tuple[str, bool]] = []
        self.upload_file_result = upload_file_result
        self.contact_id = contact_id
        self.contact_phone = contact_phone

    def get_deal(self, deal_id):
        return {"ID": deal_id}

    def get_authorization_status(self, deal):
        return self.authorization_status

    def set_authorization_status(self, deal_id, status):
        self.status_updates.append((deal_id, status))

    def add_comment(self, deal_id, comment):
        self.comments.append((deal_id, comment))
        return 1

    def upload_file(self, folder_id, filename, content):
        self.uploaded_files.append((folder_id, filename, content))
        return self.upload_file_result

    def get_deal_contact_id(self, deal):
        return self.contact_id

    def get_contact(self, contact_id):
        return {"ID": contact_id}

    def get_contact_phone(self, contact):
        return self.contact_phone

    def update_property_listing(self, deal_id, listing):
        self.property_listing_updates.append((deal_id, listing))

    def set_bot_active(self, deal_id, active):
        self.bot_active_updates.append((deal_id, active))


class FakeWahaClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id, text, session=None):
        self.calls.append((chat_id, text, session))
        return True


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


@pytest.fixture(autouse=True)
def _form_link_secret(monkeypatch):
    monkeypatch.setattr("app.forms.router.load_form_link_secret", lambda: _LINK_SECRET)


@pytest.fixture(autouse=True)
def _drive_folder_id(monkeypatch):
    monkeypatch.setattr("app.forms.router.load_signed_form_drive_folder_id", lambda: "595608")


def _signature_data_url() -> str:
    img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 20))
    img.set_rect(img.irect, (0, 0, 0))
    b64 = base64.b64encode(img.tobytes("png")).decode()
    return f"data:image/png;base64,{b64}"


def _photo_data_url() -> str:
    photo = np.full((80, 200, 3), 245, dtype=np.uint8)
    cv2.line(photo, (10, 60), (180, 15), (20, 20, 20), 4)
    ok, jpg = cv2.imencode(".jpg", photo)
    assert ok
    b64 = base64.b64encode(jpg.tobytes()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _valid_form_payload() -> dict:
    return {
        "interested_party": "Juan Pérez",
        "id_number": "1234567890",
        "email": "juan@example.com",
        "property_type": "Apartamento",
        "address": "Calle 10 #20-30",
        "location": "El Poblado, Medellín, Antioquia",
        "registration_number": "001-12345",
        "sale_price": "500000000",
        "mortgage_loan": "no",
        "leasing": "no",
        "term_months": "6",
        "signer_id_number": "1234567890",
        "signature_png": _signature_data_url(),
    }


def test_get_form_links_to_template_instead_of_embedding_pages():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # El documento se linkea (liviano), ya no se embeben las páginas como
    # imágenes base64 dentro del HTML.
    assert '__TEMPLATE_PATH_URL__' not in response.text
    assert "/formularios/autorizacion-de-corretaje/plantilla.pdf" in response.text
    assert "document-cta" in response.text
    assert "data:image/png;base64," not in response.text
    # Sección de firma con pestañas dibujar/subir foto.
    assert 'id="tab-draw"' in response.text
    assert 'id="tab-upload"' in response.text
    # Overlay que bloquea el canvas mientras se procesa una foto subida.
    assert 'id="signature-processing-overlay"' in response.text


def test_get_form_embeds_deal_id_and_token_as_hidden_fields_when_present(monkeypatch):
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FakeCrmClient())

    response = client.get(f"/formularios/autorizacion-de-corretaje?deal_id=42&token={_token_for('42')}")

    assert response.status_code == 200
    assert '<input type="hidden" name="deal_id" value="42">' in response.text
    assert f'<input type="hidden" name="token" value="{_token_for("42")}">' in response.text


def test_get_form_has_no_deal_id_field_when_absent():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'name="deal_id"' not in response.text


def test_get_form_rejects_deal_id_without_valid_token(monkeypatch):
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FakeCrmClient())

    response = client.get("/formularios/autorizacion-de-corretaje?deal_id=42")

    assert response.status_code == 200
    assert "Enlace no válido" in response.text
    assert 'name="deal_id"' not in response.text


def test_get_form_rejects_token_for_a_different_deal(monkeypatch):
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FakeCrmClient())

    response = client.get(f"/formularios/autorizacion-de-corretaje?deal_id=42&token={_token_for('99')}")

    assert response.status_code == 200
    assert "Enlace no válido" in response.text


def test_get_form_shows_already_signed_message_when_deal_is_signed(monkeypatch):
    monkeypatch.setattr(
        "app.forms.router.get_crm_client", lambda: FakeCrmClient(authorization_status="firmada")
    )

    response = client.get(f"/formularios/autorizacion-de-corretaje?deal_id=42&token={_token_for('42')}")

    assert response.status_code == 200
    assert "ya fue firmada" in response.text
    assert 'id="authorization-form"' not in response.text


def test_get_template_pdf():
    response = client.get("/formularios/autorizacion-de-corretaje/plantilla.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Plantilla" in response.headers["content-disposition"]


def test_post_clean_signature_photo_returns_cleaned_png():
    response = client.post(
        "/formularios/autorizacion-de-corretaje/limpiar-firma",
        json={"image_png": _photo_data_url()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cleaned_png"].startswith("data:image/png;base64,")


def test_post_clean_signature_photo_rejects_bad_data_url():
    response = client.post(
        "/formularios/autorizacion-de-corretaje/limpiar-firma",
        json={"image_png": "not-a-data-url"},
    )

    assert response.status_code == 400


def test_post_clean_signature_photo_rejects_oversized_payload():
    huge_data_url = "data:image/png;base64," + ("A" * 15_000_000)
    response = client.post(
        "/formularios/autorizacion-de-corretaje/limpiar-firma",
        json={"image_png": huge_data_url},
    )

    assert response.status_code == 422


def test_post_clean_signature_photo_is_rate_limited():
    payload = {"image_png": _photo_data_url()}

    responses = [
        client.post("/formularios/autorizacion-de-corretaje/limpiar-firma", json=payload) for _ in range(16)
    ]

    assert responses[-1].status_code == 429
    assert any(r.status_code == 200 for r in responses)


def test_post_form_generates_signed_pdf():
    response = client.post("/formularios/autorizacion-de-corretaje", json=_valid_form_payload())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Firmada" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_post_form_cleans_dirty_input():
    payload = _valid_form_payload()
    payload["interested_party"] = "  juan   PÉREZ gómez  "
    payload["id_number"] = "1.234.567.890"
    payload["email"] = "  Juan@Example.COM "
    payload["sale_price"] = "$ 500.000.000"
    payload["registration_number"] = "  001 12345  "

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "field",
    ["interested_party", "id_number", "email", "address", "location", "registration_number", "signer_id_number"],
)
def test_post_form_rejects_missing_required_field(field):
    payload = _valid_form_payload()
    del payload[field]

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,bad_value", [("sale_price", -5), ("outstanding_debt", -1), ("term_months", 0), ("term_months", 200)]
)
def test_post_form_rejects_out_of_range_amount_sent_as_raw_json_number(field, bad_value):
    payload = _valid_form_payload()
    payload[field] = bad_value

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_rejects_invalid_id_number():
    payload = _valid_form_payload()
    payload["id_number"] = "AB#123456"  # símbolo no permitido (letras/números/guion sí)

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_accepts_alphanumeric_id_number_with_hyphen():
    payload = _valid_form_payload()
    payload["id_number"] = "ab-123456"  # pasaporte/CE extranjero: letras + guion

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "bad_email",
    ["no-es-un-correo", "juan@", "@example.com", "juan@example", "juan@@example.com",
     "juan example.com", "juan@example..com", "juan@example.c", "juan@.com"],
)
def test_post_form_rejects_invalid_email(bad_email):
    payload = _valid_form_payload()
    payload["email"] = bad_email

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_rejects_letters_before_the_office_code(monkeypatch):
    payload = _valid_form_payload()
    payload["registration_number"] = "ABC-12345"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_accepts_letter_in_office_code(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")
    payload["registration_number"] = "50C-1945945"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    _, listing = fake_crm.property_listing_updates[0]
    assert listing.registration_number == "50C-1945945"


def test_post_form_rejects_unknown_property_type():
    payload = _valid_form_payload()
    payload["property_type"] = "Bicicleta"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_requires_mortgage_loan_and_leasing_choice():
    payload = _valid_form_payload()
    del payload["mortgage_loan"]

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_accepts_blank_optional_fields():
    payload = _valid_form_payload()
    payload["sale_price"] = ""
    payload["outstanding_debt"] = ""
    payload["term_months"] = ""

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200


def test_post_form_defaults_blank_amounts_instead_of_leaving_them_empty(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")
    payload["sale_price"] = ""

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    _, listing = fake_crm.property_listing_updates[0]
    assert listing.expected_sale_price == 0


def test_post_form_rejects_blank_registration_number():
    payload = _valid_form_payload()
    payload["registration_number"] = ""

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


def test_post_form_without_signature_is_rejected():
    payload = _valid_form_payload()
    payload["signature_png"] = ""

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 400


def test_post_form_is_rate_limited():
    payload = _valid_form_payload()

    responses = [client.post("/formularios/autorizacion-de-corretaje", json=payload) for _ in range(8)]

    assert responses[-1].status_code == 429
    assert any(r.status_code == 200 for r in responses)


def test_post_form_with_deal_id_adds_bitrix_comment_and_marks_signed(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert len(fake_crm.comments) == 2
    deal_id, comment = fake_crm.comments[0]
    assert deal_id == "42"
    assert "firm" in comment.lower()
    assert fake_crm.status_updates == [("42", "firmada")]
    assert fake_crm.bot_active_updates == [("42", False)]
    assert len(fake_crm.property_listing_updates) == 1
    listing_deal_id, listing = fake_crm.property_listing_updates[0]
    assert listing_deal_id == "42"
    assert listing.property_type == "Apartamento"
    assert listing.address == "CALLE 10 #20-30"
    assert listing.expected_sale_price == 500_000_000
    assert listing.registration_number == "001-12345"


def test_post_form_with_deal_id_pauses_bot_when_signed(monkeypatch):
    """Al firmar la Autorización de Corretaje, el bot de WhatsApp se pausa — de ahí en
    adelante debe atenderlo un asesor, no seguir conversando sobre datos que ya no aplican."""
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert fake_crm.bot_active_updates == [("42", False)]
    pause_comment = fake_crm.comments[-1][1]
    assert "pausado" in pause_comment.lower()


def test_post_form_with_deal_id_notifies_client_by_whatsapp_when_signed(monkeypatch):
    fake_crm = FakeCrmClient(contact_id="7", contact_phone="573001112233")
    fake_waha = FakeWahaClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.router.get_waha_client", lambda: fake_waha)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert len(fake_waha.calls) == 1
    chat_id, text, _ = fake_waha.calls[0]
    assert chat_id == "573001112233@c.us"
    assert "firmada" in text.lower() or "firm" in text.lower()


def test_post_form_still_marks_signed_when_whatsapp_notification_fails(monkeypatch):
    fake_crm = FakeCrmClient(contact_id="7", contact_phone="573001112233")

    def _broken_waha_client():
        raise RuntimeError("Waha no configurado")

    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.router.get_waha_client", _broken_waha_client)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert fake_crm.status_updates == [("42", "firmada")]


def test_post_form_does_not_notify_when_contact_has_no_phone(monkeypatch):
    fake_crm = FakeCrmClient(contact_id="7", contact_phone=None)
    fake_waha = FakeWahaClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.router.get_waha_client", lambda: fake_waha)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert fake_waha.calls == []


def test_post_form_with_deal_id_uploads_pdf_to_drive_and_links_it_in_comment(monkeypatch):
    fake_crm = FakeCrmClient(upload_file_result="https://example.bitrix24.com/docs/file/firmado.pdf")
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert len(fake_crm.uploaded_files) == 1
    folder_id, filename, content = fake_crm.uploaded_files[0]
    assert folder_id == "595608"
    assert filename.startswith("Autorizacion_42_")
    assert filename.endswith(".pdf")
    assert content == response.content

    _, comment = fake_crm.comments[0]
    assert "https://example.bitrix24.com/docs/file/firmado.pdf" in comment


def test_post_form_without_deal_id_does_not_upload_to_drive(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    response = client.post("/formularios/autorizacion-de-corretaje", json=_valid_form_payload())

    assert response.status_code == 200
    assert fake_crm.uploaded_files == []


def test_post_form_still_marks_signed_when_drive_upload_fails(monkeypatch):
    fake_crm = FakeCrmClient(upload_file_result=None)
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert fake_crm.status_updates == [("42", "firmada")]
    _, comment = fake_crm.comments[0]
    assert "http" not in comment


def test_post_form_rejects_deal_id_without_valid_token(monkeypatch):
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FakeCrmClient())

    payload = _valid_form_payload()
    payload["deal_id"] = "42"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 403


def test_post_form_rejects_already_signed_deal(monkeypatch):
    monkeypatch.setattr(
        "app.forms.router.get_crm_client", lambda: FakeCrmClient(authorization_status="firmada")
    )

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 409


def test_post_form_without_deal_id_does_not_touch_bitrix(monkeypatch):
    def fail_if_called():
        raise AssertionError("no debería construirse un cliente de CRM sin deal_id")

    monkeypatch.setattr("app.forms.router.get_crm_client", fail_if_called)

    response = client.post("/formularios/autorizacion-de-corretaje", json=_valid_form_payload())

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_post_form_still_returns_pdf_when_bitrix_comment_fails(monkeypatch):
    class FailingCrmClient(FakeCrmClient):
        def add_comment(self, deal_id, comment):
            raise RuntimeError("Bitrix caído")

    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FailingCrmClient())

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
