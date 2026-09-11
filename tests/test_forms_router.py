from __future__ import annotations

import base64

import cv2
import pymupdf as fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.shared.rate_limit as rate_limit_module
from app.forms.link_token import sign_deal_id
from app.main import app
from app.xposure.models import PropertySearchResult
from tests.fakes import FakeCrmClient as _SharedFakeCrmClient

client = TestClient(app)


class FakeXposureClient:
    def __init__(self, result: PropertySearchResult) -> None:
        self._result = result

    def resolve_area_code(self, office_code: str) -> str | None:
        return office_code.strip().upper()

    def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None) -> PropertySearchResult:
        return self._result

_LINK_SECRET = "test-secret"
_DEAL_ID = "42"


def _token_for(deal_id: str) -> str:
    return sign_deal_id(deal_id, _LINK_SECRET)


def FakeCrmClient(
    *,
    authorization_status: str | None = None,
    upload_file_result: str | None = "https://example.bitrix24.com/docs/file/firmado.pdf",
    contact_id: str | None = "7",
    contact_phone: str | None = "573001112233",
) -> _SharedFakeCrmClient:
    """Arma `tests.fakes.FakeCrmClient` (compartido entre todos los tests) con el único deal
    ("42") que usa este archivo, en vez de mantener una redefinición local del mismo fake."""
    deal: dict[str, object] = {}
    if authorization_status is not None:
        deal["AUTHORIZATION_STATUS"] = authorization_status
    if contact_id is not None:
        deal["CONTACT_ID"] = contact_id

    contacts: dict[str, dict[str, object]] = {}
    if contact_id is not None:
        contacts[contact_id] = {"PHONE": contact_phone} if contact_phone is not None else {}

    fake = _SharedFakeCrmClient(deals={_DEAL_ID: deal}, contacts=contacts)
    fake.upload_file_result = upload_file_result
    return fake


class FakeWahaClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id, text, session=None):
        self.calls.append((chat_id, text, session))
        return True

    def get_chat_messages(self, chat_id, *, limit=50, from_me=None, session=None):
        return []


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
    monkeypatch.setattr("app.flows.brokerage_authorization_signed.load_signed_form_drive_folder_id", lambda: "595608")


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
        "location_sector_code": "41001",
        "registration_number": "001-12345",
        "sale_price": "500000000",
        "mortgage_loan": "no",
        "leasing": "no",
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


def test_get_form_shows_authorization_step_before_full_form():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'id="wizard-step-authorization"' in response.text
    assert 'id="wizard-authorize-yes"' in response.text
    assert 'id="wizard-authorize-no"' in response.text
    # El formulario completo arranca oculto hasta pasar el wizard.
    assert 'id="full-form-card" class="card card--hidden"' in response.text


def test_get_form_requires_data_treatment_consent_checkbox():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'id="wizard-data-consent"' in response.text
    assert "Ley 1581 de 2012" in response.text


def test_get_form_links_to_official_law_text():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'href="https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981"' in response.text
    assert 'target="_blank"' in response.text
    # La pregunta vieja ya no está: el enlace a la ley reemplaza la pregunta.
    assert "¿Autorizas a Alberto Álvarez a representarte" not in response.text


def test_get_form_declined_step_uses_centered_success_view_style():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'class="card success-view card--hidden" id="wizard-step-declined"' in response.text
    assert "success-view__icon--info" in response.text


def test_get_form_location_field_lives_only_in_the_wizard_step():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'id="wizard-step-location"' in response.text
    # No debe pedirse dos veces: solo aparece dentro del paso del wizard.
    assert response.text.count('name="location"') == 1
    assert 'id="field-location"' in response.text


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
    [
        "interested_party",
        "id_number",
        "email",
        "address",
        "location",
        "location_sector_code",
        "registration_number",
        "signer_id_number",
    ],
)
def test_post_form_rejects_missing_required_field(field):
    payload = _valid_form_payload()
    del payload[field]

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("field,bad_value", [("sale_price", -5), ("outstanding_debt", -1)])
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
    assert fake_crm.authorization_status_updates == [("42", "firmada")]
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
    import app.forms.router as forms_router_module

    fake_crm = FakeCrmClient(contact_id="7", contact_phone="573001112233")
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert forms_router_module.conversation_store.get_bot_enabled("573001112233@c.us") is False
    assert (
        forms_router_module.conversation_store.get_bot_enabled_reason("573001112233@c.us") == "authorization_signed"
    )
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
    assert fake_crm.authorization_status_updates == [("42", "firmada")]


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
    assert fake_crm.authorization_status_updates == [("42", "firmada")]
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
    fake_crm = FakeCrmClient()

    def _failing_add_comment(deal_id, comment):
        raise RuntimeError("Bitrix caído")

    fake_crm.add_comment = _failing_add_comment
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    payload = _valid_form_payload()
    payload["deal_id"] = "42"
    payload["token"] = _token_for("42")

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


_VERIFY_MATRICULA_PATH = "/formularios/autorizacion-de-corretaje/verify-matricula"


def test_verify_matricula_blocks_when_already_published_in_xposure(monkeypatch):
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )
    monkeypatch.setattr("app.forms.router.get_xposure_client", lambda: fake_xposure)

    response = client.post(_VERIFY_MATRICULA_PATH, json={"registration_number": "50C-1945945"})

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is True
    assert body["exact_match"] is True
    assert body["message"] != ""


def test_verify_matricula_allows_when_not_found_in_xposure(monkeypatch):
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="123456", exists=False, reason="No se encontraron resultados")
    )
    monkeypatch.setattr("app.forms.router.get_xposure_client", lambda: fake_xposure)

    response = client.post(_VERIFY_MATRICULA_PATH, json={"registration_number": "001-123456"})

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert body["message"] == ""


def test_verify_matricula_rejects_invalid_format():
    response = client.post(_VERIFY_MATRICULA_PATH, json={"registration_number": "ABC1234"})

    assert response.status_code == 422


def test_verify_matricula_with_deal_id_does_not_touch_bitrix_before_client_confirms(monkeypatch):
    # El wizard le pregunta al cliente "¿es este tu inmueble?" antes de
    # bloquear — /verify-matricula ya no marca Duplicado ni comenta en Bitrix
    # por su cuenta, eso lo hace /confirm-matricula-match una vez responde
    # (ver los tests de ese endpoint más abajo).
    fake_crm = FakeCrmClient()
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.router.get_xposure_client", lambda: fake_xposure)

    response = client.post(
        _VERIFY_MATRICULA_PATH,
        json={"registration_number": "50C-1945945", "deal_id": "42", "token": _token_for("42")},
    )

    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert fake_crm.duplicado_updates == []
    assert fake_crm.pins == []
    assert fake_crm.comments == []


def test_verify_matricula_rejects_deal_id_without_valid_token(monkeypatch):
    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="1945945", exists=False))
    monkeypatch.setattr("app.forms.router.get_xposure_client", lambda: fake_xposure)

    response = client.post(
        _VERIFY_MATRICULA_PATH, json={"registration_number": "50C-1945945", "deal_id": "42"}
    )

    assert response.status_code == 403


def test_verify_matricula_without_deal_id_does_not_touch_bitrix(monkeypatch):
    def fail_if_called():
        raise AssertionError("no debería construirse un cliente de CRM sin deal_id")

    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="1945945", exists=False))
    monkeypatch.setattr("app.forms.router.get_crm_client", fail_if_called)
    monkeypatch.setattr("app.forms.router.get_xposure_client", lambda: fake_xposure)

    response = client.post(_VERIFY_MATRICULA_PATH, json={"registration_number": "50C-1945945"})

    assert response.status_code == 200


def test_verify_matricula_is_rate_limited(monkeypatch):
    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="1945945", exists=False))
    monkeypatch.setattr("app.forms.router.get_xposure_client", lambda: fake_xposure)

    responses = [
        client.post(_VERIFY_MATRICULA_PATH, json={"registration_number": "50C-1945945"}) for _ in range(16)
    ]

    assert responses[-1].status_code == 429
    assert any(r.status_code == 200 for r in responses)


_CONFIRM_MATRICULA_MATCH_PATH = "/formularios/autorizacion-de-corretaje/confirm-matricula-match"


def test_confirm_matricula_match_confirmed_marks_duplicado_and_pins(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    response = client.post(
        _CONFIRM_MATRICULA_MATCH_PATH,
        json={
            "registration_number": "50C-1945945",
            "url": "https://example.com/999",
            "confirmed": True,
            "deal_id": "42",
            "token": _token_for("42"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert fake_crm.duplicado_updates == [("42", True)]
    assert len(fake_crm.pins) == 1


def test_confirm_matricula_match_not_confirmed_marks_sin_duplicado_without_pin(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    response = client.post(
        _CONFIRM_MATRICULA_MATCH_PATH,
        json={
            "registration_number": "50C-1945945",
            "url": "https://example.com/999",
            "confirmed": False,
            "deal_id": "42",
            "token": _token_for("42"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert fake_crm.duplicado_updates == [("42", False)]
    assert fake_crm.pins == []


def test_confirm_matricula_match_rejects_deal_id_without_valid_token():
    response = client.post(
        _CONFIRM_MATRICULA_MATCH_PATH,
        json={"registration_number": "50C-1945945", "confirmed": True, "deal_id": "42"},
    )

    assert response.status_code == 403


def test_confirm_matricula_match_without_deal_id_does_not_touch_bitrix():
    def fail_if_called():
        raise AssertionError("no debería construirse un cliente de CRM sin deal_id")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.forms.router.get_crm_client", fail_if_called)
        response = client.post(
            _CONFIRM_MATRICULA_MATCH_PATH,
            json={"registration_number": "50C-1945945", "confirmed": True},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_confirm_matricula_match_is_rate_limited(monkeypatch):
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: fake_crm)

    responses = [
        client.post(_CONFIRM_MATRICULA_MATCH_PATH, json={"registration_number": "50C-1945945", "confirmed": True})
        for _ in range(16)
    ]

    assert responses[-1].status_code == 429


_VERIFY_COBERTURA_PATH = "/formularios/autorizacion-de-corretaje/verify-cobertura"


def test_verify_cobertura_allows_when_sector_is_covered(monkeypatch):
    monkeypatch.setattr("app.forms.router.is_location_covered", lambda sector_code: True)

    response = client.post(_VERIFY_COBERTURA_PATH, json={"sector_code": "41001"})

    assert response.status_code == 200
    assert response.json() == {"covered": True}


def test_verify_cobertura_blocks_when_sector_is_not_covered(monkeypatch):
    monkeypatch.setattr("app.forms.router.is_location_covered", lambda sector_code: False)

    response = client.post(_VERIFY_COBERTURA_PATH, json={"sector_code": "00081"})

    assert response.status_code == 200
    body = response.json()
    assert body["covered"] is False
    assert body["message"] != ""


def test_verify_cobertura_allows_when_check_cannot_be_determined(monkeypatch):
    # Contrato: is_location_covered ya resuelve el caso ambiguo (DWH caído,
    # sector_code no reconocido) dejando pasar al cliente — este endpoint
    # solo refleja lo que esa función devuelva.
    monkeypatch.setattr("app.forms.router.is_location_covered", lambda sector_code: True)

    response = client.post(_VERIFY_COBERTURA_PATH, json={"sector_code": "no-reconocido"})

    assert response.status_code == 200
    assert response.json() == {"covered": True}


def test_verify_cobertura_rejects_missing_sector_code():
    response = client.post(_VERIFY_COBERTURA_PATH, json={"sector_code": ""})

    assert response.status_code == 422


def test_verify_cobertura_does_not_touch_crm(monkeypatch):
    def fail_if_called():
        raise AssertionError("verify-cobertura no debería construir un cliente de CRM")

    monkeypatch.setattr("app.forms.router.get_crm_client", fail_if_called)
    monkeypatch.setattr("app.forms.router.is_location_covered", lambda sector_code: False)

    response = client.post(_VERIFY_COBERTURA_PATH, json={"sector_code": "00081"})

    assert response.status_code == 200


def test_verify_cobertura_is_rate_limited(monkeypatch):
    monkeypatch.setattr("app.forms.router.is_location_covered", lambda sector_code: True)

    responses = [client.post(_VERIFY_COBERTURA_PATH, json={"sector_code": "41001"}) for _ in range(16)]

    assert responses[-1].status_code == 429
    assert any(r.status_code == 200 for r in responses)


_ESTADO_SERVICIOS_PATH = "/formularios/autorizacion-de-corretaje/estado-servicios"


def test_estado_servicios_reports_both_services_up(monkeypatch):
    monkeypatch.setattr("app.forms.router.location_catalog_client.is_reachable", lambda: True)
    monkeypatch.setattr("app.forms.router._is_xposure_reachable", lambda: True)

    response = client.get(_ESTADO_SERVICIOS_PATH)

    assert response.status_code == 200
    assert response.json() == {"mobilia_dwh": True, "xposure": True}


def test_estado_servicios_reports_mobilia_dwh_down(monkeypatch):
    monkeypatch.setattr("app.forms.router.location_catalog_client.is_reachable", lambda: False)
    monkeypatch.setattr("app.forms.router._is_xposure_reachable", lambda: True)

    response = client.get(_ESTADO_SERVICIOS_PATH)

    assert response.status_code == 200
    assert response.json() == {"mobilia_dwh": False, "xposure": True}


def test_estado_servicios_reports_xposure_down(monkeypatch):
    monkeypatch.setattr("app.forms.router.location_catalog_client.is_reachable", lambda: True)
    monkeypatch.setattr("app.forms.router._is_xposure_reachable", lambda: False)

    response = client.get(_ESTADO_SERVICIOS_PATH)

    assert response.status_code == 200
    assert response.json() == {"mobilia_dwh": True, "xposure": False}


def test_estado_servicios_is_rate_limited(monkeypatch):
    monkeypatch.setattr("app.forms.router.location_catalog_client.is_reachable", lambda: True)
    monkeypatch.setattr("app.forms.router._is_xposure_reachable", lambda: True)

    responses = [client.get(_ESTADO_SERVICIOS_PATH) for _ in range(31)]

    assert responses[-1].status_code == 429
    assert any(r.status_code == 200 for r in responses)
    assert any(r.status_code == 200 for r in responses)
