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
