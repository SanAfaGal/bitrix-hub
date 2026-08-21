from __future__ import annotations

import base64

import cv2
import fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.forms.rate_limit as rate_limit_module
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


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
        "municipality": "Medellín",
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


def test_get_form_embeds_deal_id_as_hidden_field_when_present():
    response = client.get("/formularios/autorizacion-de-corretaje?deal_id=42")

    assert response.status_code == 200
    assert '<input type="hidden" name="deal_id" value="42">' in response.text


def test_get_form_has_no_deal_id_field_when_absent():
    response = client.get("/formularios/autorizacion-de-corretaje")

    assert response.status_code == 200
    assert 'name="deal_id"' not in response.text


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
    "field", ["interested_party", "id_number", "email", "address", "municipality", "signer_id_number"]
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
    payload["id_number"] = "abc123"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


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


def test_post_form_rejects_letters_in_registration_number():
    payload = _valid_form_payload()
    payload["registration_number"] = "ABC-12345"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 422


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
    payload["registration_number"] = ""
    payload["sale_price"] = ""
    payload["term_months"] = ""

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200


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


def test_post_form_with_deal_id_adds_bitrix_comment(monkeypatch):
    calls = []

    class FakeCrmClient:
        def add_comment(self, deal_id, comment):
            calls.append((deal_id, comment))
            return 1

    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FakeCrmClient())

    payload = _valid_form_payload()
    payload["deal_id"] = "42"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert len(calls) == 1
    deal_id, comment = calls[0]
    assert deal_id == "42"
    assert "firm" in comment.lower()


def test_post_form_without_deal_id_does_not_touch_bitrix(monkeypatch):
    def fail_if_called():
        raise AssertionError("no debería construirse un cliente de CRM sin deal_id")

    monkeypatch.setattr("app.forms.router.get_crm_client", fail_if_called)

    response = client.post("/formularios/autorizacion-de-corretaje", json=_valid_form_payload())

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_post_form_still_returns_pdf_when_bitrix_comment_fails(monkeypatch):
    class FailingCrmClient:
        def add_comment(self, deal_id, comment):
            raise RuntimeError("Bitrix caído")

    monkeypatch.setattr("app.forms.router.get_crm_client", lambda: FailingCrmClient())

    payload = _valid_form_payload()
    payload["deal_id"] = "42"

    response = client.post("/formularios/autorizacion-de-corretaje", json=payload)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
