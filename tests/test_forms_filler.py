import base64
import io

import fitz
import pytest

from app.forms.filler import build_blank_template, decode_signature_png, fill_and_sign


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


def test_build_blank_template_has_no_field_values():
    pdf_bytes = build_blank_template()

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        for page in doc:
            for widget in page.widgets() or []:
                assert not widget.field_value
                assert not widget.field_flags & fitz.PDF_FIELD_IS_READ_ONLY
    finally:
        doc.close()


def test_fill_and_sign_writes_field_values_and_signature():
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
        filled = {}
        for page in doc:
            for widget in page.widgets() or []:
                filled[widget.field_name] = widget.field_value
                assert widget.field_flags & fitz.PDF_FIELD_IS_READ_ONLY

        assert filled["Text2"] == "Juan Pérez"
        assert filled["Text3"] == "1234567890"
        assert filled["Text17"] == "1234567890"

        signature_page = doc[1]
        images = signature_page.get_images(full=True)
        assert len(images) >= 1
    finally:
        doc.close()


def test_fill_and_sign_sets_signing_date_from_server_ignoring_client_input():
    values = {"signing_day": "1", "signing_month": "enero", "signing_year": "2000"}
    signature_png_bytes = decode_signature_png(_signature_png_data_url())

    pdf_bytes = fill_and_sign(values, signature_png_bytes)

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        filled = {}
        for page in doc:
            for widget in page.widgets() or []:
                filled[widget.field_name] = widget.field_value

        assert filled["Text16"] != "2000"
        assert filled["Text16"]
        assert filled["Text15"]
        assert filled["Text14"]
    finally:
        doc.close()
