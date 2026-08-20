"""Relleno y firma del PDF de Autorización de Corretaje (AcroForm + imagen de firma)."""
from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import fitz  # PyMuPDF

TEMPLATE_PATH = Path(__file__).parent / "templates" / "brokerage_authorization.pdf"

_BOGOTA_TZ = ZoneInfo("America/Bogota")
_SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Mapeo de campo lógico -> nombre de widget AcroForm en la plantilla.
FIELD_MAP: dict[str, str] = {
    "interested_party": "Text2",
    "id_number": "Text3",
    "email": "Text4",
    "property_type": "Text5",
    "address": "Text6",
    "municipality": "Text7",
    "registration_number": "Text8",
    "sale_price": "Text9",
    "mortgage_loan": "Text10",
    "leasing": "Text11",
    "outstanding_debt": "Text12",
    "term_months": "Text13",
    "signing_day": "Text14",
    "signing_month": "Text15",
    "signing_year": "Text16",
    "signer_id_number": "Text17",
}
_WIDGET_TO_LOGICAL_NAME = {widget_name: logical for logical, widget_name in FIELD_MAP.items()}

# Página (0-index) y rect (coords top-left de PyMuPDF) donde va la firma del interesado.
SIGNATURE_PAGE = 1
SIGNATURE_RECT = fitz.Rect(50, 615, 260, 678)

# Aire alrededor de la firma dentro de ese rect: sin esto, una firma que
# llena bien el recuadro queda pegada a las líneas del documento (renglón de
# firma / texto de abajo), no se ve como una firma "puesta encima" del papel.
SIGNATURE_MARGIN = 6

_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg);base64,(.+)$")


def decode_signature_png(data_url: str) -> bytes:
    """Decodifica el `data:image/png;base64,...` que produce `canvas.toDataURL()`."""
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValueError("Firma inválida: se esperaba un data URL de imagen PNG/JPEG en base64.")
    return base64.b64decode(match.group(2))


def build_blank_template() -> bytes:
    """Re-serializa la plantilla AcroForm (sin diligenciar) para descarga y pruebas."""
    doc = fitz.open(TEMPLATE_PATH)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def _signing_date_values() -> dict[str, str]:
    """Fecha de firma tomada del servidor (hora Bogotá), nunca del cliente."""
    now = datetime.now(_BOGOTA_TZ)
    return {
        "signing_day": str(now.day),
        "signing_month": _SPANISH_MONTHS[now.month - 1],
        "signing_year": str(now.year),
    }


def fill_and_sign(values: dict[str, str], signature_png_bytes: bytes) -> bytes:
    """Rellena los campos del AcroForm, inserta la firma y devuelve el PDF resultante en bytes.

    La fecha de firma se calcula acá, no se toma del payload del cliente.
    """
    values = {**values, **_signing_date_values()}
    doc = fitz.open(TEMPLATE_PATH)
    try:
        for page in doc:
            for widget in page.widgets() or []:
                field_value = values.get(_WIDGET_TO_LOGICAL_NAME.get(widget.field_name))
                if field_value is not None:
                    widget.field_value = field_value
                widget.field_flags |= fitz.PDF_FIELD_IS_READ_ONLY
                widget.update()

        signature_rect = SIGNATURE_RECT + (
            SIGNATURE_MARGIN,
            SIGNATURE_MARGIN,
            -SIGNATURE_MARGIN,
            -SIGNATURE_MARGIN,
        )
        doc[SIGNATURE_PAGE].insert_image(signature_rect, stream=signature_png_bytes)

        return doc.tobytes()
    finally:
        doc.close()
