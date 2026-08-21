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
    "interested_party": _Field(0, (150.26, 99.22, 328.30, 108.96), (150.26, 107.30), 8),
    "id_number": _Field(0, (120.62, 108.94, 252.77, 118.68), (120.62, 117.02), 8),
    "email": _Field(0, (128.42, 118.66, 306.60, 128.40), (128.42, 126.74), 8),
    "property_type": _Field(0, (160.70, 239.74, 293.08, 249.48), (160.70, 247.82), 8),
    "address": _Field(0, (128.53, 249.46, 281.28, 259.20), (128.53, 257.54), 8),
    "municipality": _Field(0, (129.02, 259.18, 230.88, 268.92), (129.02, 267.26), 8),
    "registration_number": _Field(0, (177.60, 268.90, 289.59, 278.64), (177.60, 276.98), 8),
    # "$" es texto propio de la plantilla, pegado al subrayado (mismo span) —
    # se deja intacto y el borrado empieza justo después, en el primer "_".
    "sale_price": _Field(0, (208.64, 278.65, 295.20, 288.39), (208.64, 286.73), 8),
    "mortgage_loan": _Field(0, (168.72, 288.37, 209.46, 298.11), (168.72, 296.45), 8),
    "leasing": _Field(0, (122.06, 298.09, 162.69, 307.83), (122.06, 306.17), 8),
    "outstanding_debt": _Field(0, (253.25, 307.81, 344.85, 317.55), (253.25, 315.89), 8),
    "term_months": _Field(0, (263.33, 380.29, 274.68, 390.03), (263.33, 388.37), 8),
    "signing_day": _Field(1, (256.25, 583.35, 276.60, 593.09), (256.25, 591.43), 8),
    "signing_month": _Field(1, (345.31, 583.35, 396.24, 593.09), (345.31, 591.43), 8),
    "signing_year": _Field(1, (431.35, 583.35, 471.98, 593.09), (431.35, 591.43), 8),
    # No hay subrayado tras "CC." (queda en blanco en el diseño); el punto
    # base se toma directo del `origin` de ese mismo renglón ("CC. ").
    "signer_id_number": _Field(1, (105.29, 693.05, 270.0, 705.12), (108.3, 703.06), 8),
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
