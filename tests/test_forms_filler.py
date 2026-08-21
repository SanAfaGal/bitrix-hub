import base64
import io

import fitz
import pytest

from app.forms.filler import SIGNATURE_RECT, build_blank_template, decode_signature_png, fill_and_sign

# No se importa SIGNATURE_MARGIN de filler.py a propósito: si el test usara
# esa misma constante para calcular lo esperado, pasaría igual aunque el
# margen real fuera 0 — comprobaría consistencia, no que exista margen.
_MIN_EXPECTED_MARGIN = 3


def _signature_png_data_url() -> str:
    img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 20))
    img.set_rect(img.irect, (0, 0, 0))
    png_bytes = img.tobytes("png")
    b64 = base64.b64encode(png_bytes).decode()
    return f"data:image/png;base64,{b64}"


def test_decode_signature_png_valid():
    data_url = _signature_png_data_url()
    decoded = decode_signature_png(data_url)
    assert decoded.startswith(b"\x89PNG")


def test_decode_signature_png_invalid():
    with pytest.raises(ValueError):
        decode_signature_png("not-a-data-url")


def test_build_blank_template_has_no_widgets():
    # Ya no se usa AcroForm (el texto de un widget no siempre queda incluido
    # en la selección/copiado del visor de PDF) — la plantilla sin diligenciar
    # es el PDF de Word tal cual, sin campos interactivos.
    pdf_bytes = build_blank_template()

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        for page in doc:
            assert list(page.widgets() or []) == []
    finally:
        doc.close()


def test_fill_and_sign_writes_field_values_as_real_text_and_signature():
    values = {
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
    }
    signature_png_bytes = decode_signature_png(_signature_png_data_url())

    pdf_bytes = fill_and_sign(values, signature_png_bytes)

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        # Sin widgets: el valor tiene que quedar como texto normal de la
        # página (así queda seleccionable/copiable en cualquier visor).
        page0_text = doc[0].get_text()
        page1_text = doc[1].get_text()
        assert "Juan Pérez" in page0_text
        assert "1234567890" in page0_text
        assert "1234567890" in page1_text

        signature_page = doc[1]
        images = signature_page.get_images(full=True)
        assert len(images) >= 1
    finally:
        doc.close()


def test_fill_and_sign_leaves_margin_around_signature():
    # Una firma "cuadrada" que llenaría todo el recuadro si se insertara al
    # ras del rect — sirve para detectar si el margen realmente se aplicó.
    img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200))
    img.set_rect(img.irect, (0, 0, 0))
    b64 = base64.b64encode(img.tobytes("png")).decode()
    signature_png_bytes = decode_signature_png(f"data:image/png;base64,{b64}")

    pdf_bytes = fill_and_sign({}, signature_png_bytes)

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        page = doc[1]
        # La plantilla ya trae otras imágenes (logo, etc.) — nos quedamos con
        # la que cayó dentro del rect de la firma.
        bbox = next(
            page.get_image_bbox(img)
            for img in page.get_images(full=True)
            if SIGNATURE_RECT.contains(page.get_image_bbox(img))
        )

        # Sin margen a la izquierda a propósito: ese borde tiene que quedar
        # pegado al arranque de "EL INTERESADO", no centrado en el recuadro.
        assert bbox.x0 == pytest.approx(SIGNATURE_RECT.x0, abs=0.01)
        assert bbox.y0 >= SIGNATURE_RECT.y0 + _MIN_EXPECTED_MARGIN
        assert bbox.x1 <= SIGNATURE_RECT.x1 - _MIN_EXPECTED_MARGIN
        assert bbox.y1 <= SIGNATURE_RECT.y1 - _MIN_EXPECTED_MARGIN
    finally:
        doc.close()


def test_fill_and_sign_aligns_signature_left_even_when_narrower_than_box():
    # Firma angosta (mucho más ancha que alta) — si se centrara en el
    # recuadro (ancho) quedaría corrida hacia la derecha en vez de arrancar
    # junto a "EL INTERESADO".
    img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 20))
    img.set_rect(img.irect, (0, 0, 0))
    b64 = base64.b64encode(img.tobytes("png")).decode()
    signature_png_bytes = decode_signature_png(f"data:image/png;base64,{b64}")

    pdf_bytes = fill_and_sign({}, signature_png_bytes)

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        page = doc[1]
        bbox = next(
            page.get_image_bbox(img)
            for img in page.get_images(full=True)
            if SIGNATURE_RECT.contains(page.get_image_bbox(img))
        )
        assert bbox.x0 == pytest.approx(SIGNATURE_RECT.x0, abs=0.01)
    finally:
        doc.close()


def test_fill_and_sign_sets_signing_date_from_server_ignoring_client_input():
    values = {"signing_day": "1", "signing_month": "enero", "signing_year": "2000"}
    signature_png_bytes = decode_signature_png(_signature_png_data_url())

    pdf_bytes = fill_and_sign(values, signature_png_bytes)

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        page1_text = doc[1].get_text()
        assert "2000" not in page1_text
        assert "enero" not in page1_text
    finally:
        doc.close()
