"""Relleno y firma del PDF de Autorización de Corretaje (texto real + imagen de firma).

La plantilla es el PDF exportado de Word (sin AcroForm ni recuadros): cada
campo es un subrayado dentro del texto corrido. Rellenar un AcroForm ahí se
descartó porque el texto de un widget no siempre queda incluido en la capa
de selección/copiado del visor de PDF ("CC. No: ______" al copiar en vez del
valor) — acá en cambio se borra el subrayado con una redacción y se escribe
el valor como texto normal de la página, en el mismo punto base (baseline)
que ya usa el resto del documento, así queda alineado y siempre copiable.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import fitz  # PyMuPDF

TEMPLATE_PATH = Path(__file__).parent / "templates" / "AUTORIZACIÓN DE CORRETAJE INMOBILIARIO ALBERTO ÁLVAREZ.pdf"

_BOGOTA_TZ = ZoneInfo("America/Bogota")
_SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


class _Field:
    """Un campo = dónde borrar el subrayado y en qué punto base escribir encima.

    Coordenadas top-left (convención de PyMuPDF), sacadas de
    `page.get_text("rawdict")` sobre la plantilla: `erase` es el rect del
    subrayado (incluye "$" cuando el campo va después de uno, para no
    depender de su ancho exacto) y `baseline` es el `origin` del primer
    carácter de ese mismo subrayado — así el texto insertado queda sobre el
    mismo renglón que el resto del documento, no centrado en el rect.
    """

    __slots__ = ("page", "erase", "baseline", "fontsize")

    def __init__(self, page: int, erase: tuple[float, float, float, float], baseline: tuple[float, float], fontsize: int):
        self.page = page
        self.erase = fitz.Rect(*erase)
        self.baseline = fitz.Point(*baseline)
        self.fontsize = fontsize


# Campo lógico -> posición en la plantilla. Si el diseño de Word cambia (se
# mueve un campo, cambia el texto y corre los subrayados), hay que volver a
# sacar estas coordenadas con `get_text("rawdict")` sobre el PDF nuevo.
_FIELDS: dict[str, _Field] = {
    "interested_party": _Field(0, (150.3, 99.2, 318.1, 109.0), (150.26, 107.30), 8),
    "id_number": _Field(0, (120.6, 108.9, 252.8, 118.7), (120.62, 117.02), 8),
    "email": _Field(0, (128.4, 118.7, 296.4, 128.4), (128.42, 126.74), 8),
    "property_type": _Field(0, (160.7, 239.7, 293.1, 249.5), (160.70, 247.82), 8),
    "address": _Field(0, (128.5, 249.5, 260.9, 259.2), (128.53, 257.54), 8),
    "municipality": _Field(0, (307.6, 249.5, 378.8, 259.2), (307.59, 257.54), 8),
    "registration_number": _Field(0, (177.6, 259.2, 289.6, 268.9), (177.60, 267.26), 8),
    "sale_price": _Field(0, (208.7, 268.9, 295.2, 278.6), (208.73, 276.98), 8),
    "mortgage_loan": _Field(0, (168.7, 278.6, 209.5, 288.4), (168.72, 286.73), 8),
    "leasing": _Field(0, (249.3, 278.6, 289.9, 288.4), (249.29, 286.73), 8),
    "outstanding_debt": _Field(0, (195.8, 288.4, 287.4, 298.1), (195.77, 296.45), 8),
    "term_months": _Field(0, (261.5, 359.5, 276.5, 371.5), (263.33, 368.93), 8),
    "signing_day": _Field(1, (256.2, 560.8, 276.6, 570.5), (256.25, 568.87), 8),
    "signing_month": _Field(1, (345.3, 560.8, 396.2, 570.5), (345.31, 568.87), 8),
    "signing_year": _Field(1, (431.4, 560.8, 470.0, 570.5), (431.35, 568.87), 8),
    # No hay subrayado tras "CC." (queda en blanco en el diseño); el punto
    # base se calculó a partir del `origin` del último carácter de "CC. ".
    "signer_id_number": _Field(1, (105.0, 670.5, 260.0, 682.6), (108.0, 680.5), 8),
}

# Página (0-index) y rect (coords top-left de PyMuPDF) donde va la firma del interesado.
SIGNATURE_PAGE = 1
SIGNATURE_RECT = fitz.Rect(84, 606, 266, 651)

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
    """Re-serializa la plantilla (sin diligenciar) para descarga y pruebas."""
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


def _left_aligned_fit(box: fitz.Rect, image_bytes: bytes) -> fitz.Rect:
    """Rect dentro de `box` para la firma, pegada al borde izquierdo (no centrada).

    `insert_image` con el rect completo del `box` centra la imagen si su
    proporción no calza exacto (letterboxing) — eso corre la firma hacia la
    derecha cuando el trazo quedó angosto (una firma corta, o pegada a un
    lado del canvas al dibujarla). El cliente ya recorta la imagen al
    rectángulo justo de la tinta (ver `trimSignature` en `page_script.py`),
    así que acá solo hace falta calcular su tamaño real dentro de `box`
    manteniendo proporción, y anclarlo a la izquierda en vez de centrarlo.
    """
    pixmap = fitz.Pixmap(image_bytes)
    scale = min(box.width / pixmap.width, box.height / pixmap.height)
    width = pixmap.width * scale
    height = pixmap.height * scale
    y0 = box.y0 + (box.height - height) / 2
    return fitz.Rect(box.x0, y0, box.x0 + width, y0 + height)


def fill_and_sign(values: dict[str, str], signature_png_bytes: bytes) -> bytes:
    """Rellena los campos, inserta la firma y devuelve el PDF resultante en bytes.

    La fecha de firma se calcula acá, no se toma del payload del cliente.
    Los campos sin valor (opcionales que quedaron en blanco) se dejan tal
    cual están en la plantilla, con su subrayado.
    """
    values = {**values, **_signing_date_values()}
    doc = fitz.open(TEMPLATE_PATH)
    try:
        by_page: dict[int, list[tuple[_Field, str]]] = {}
        for name, field in _FIELDS.items():
            value = values.get(name)
            if value:
                by_page.setdefault(field.page, []).append((field, value))

        for page_index, items in by_page.items():
            page = doc[page_index]
            for field, _value in items:
                page.add_redact_annot(field.erase, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions()
            for field, value in items:
                page.insert_text(field.baseline, value, fontsize=field.fontsize, fontname="helv", color=(0, 0, 0))

        # Sin margen a la izquierda: ese borde ya coincide con el arranque de
        # "EL INTERESADO" en la plantilla, y la firma se alinea ahí (ver
        # `_left_aligned_fit`) en vez de quedar centrada en el recuadro.
        signature_box = SIGNATURE_RECT + (
            0,
            SIGNATURE_MARGIN,
            -SIGNATURE_MARGIN,
            -SIGNATURE_MARGIN,
        )
        signature_rect = _left_aligned_fit(signature_box, signature_png_bytes)
        doc[SIGNATURE_PAGE].insert_image(signature_rect, stream=signature_png_bytes)

        return doc.tobytes()
    finally:
        doc.close()
