"""Registro único de los campos que comparten el formulario público
(`app/forms/`) y el formulario interno (`app/interno/`) — mismo dato de
negocio, mismo título, mismo hint, misma validación y el mismo formateo en
vivo en los dos lados. Antes vivían duplicados (una copia en cada
`models.py`/plantilla/JS); ahora cada lado arma su propio `Payload` y su
propia página leyendo de acá, así que un cambio de regla o de texto se hace
en un solo lugar.

No cubre los campos que solo existe en un lado (`id_number`,
`registration_number`, `mortgage_loan`, `leasing`, `outstanding_debt` — solo
público; `owner_phone` — solo interno se agrega igual acá porque no cuesta
nada tenerlo centralizado también, aunque hoy solo lo use un consumidor).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.forms.cleaning import blank_to_none, clean_digits, clean_email, clean_name, collapse_whitespace

PROPERTY_TYPES: tuple[str, ...] = (
    "Apartamento",
    "Apartaestudio",
    "Bodega",
    "Casa",
    "Casa campestre",
    "Casa comercial",
    "Consultorio",
    "Edificio",
    "Finca",
    "Hotel",
    "Local",
    "Lote",
    "Parcelación",
    "Parqueadero",
)
PropertyType = Literal[*PROPERTY_TYPES]

_NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-\s]+$")
# "sector, ciudad, departamento" — mismo alfabeto que _NAME_RE más coma y
# punto (valores reales como "Bogotá D.C." o el formato con comas del
# catálogo de ubicaciones, ver app/location_catalog/client.py).
_LOCATION_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-,.\s]+$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@.]+(\.[^\s@.]+)*\.[a-zA-Z]{2,}$")


def validate_person_name(value: str, *, label: str, min_length: int = 3) -> str:
    cleaned = clean_name(value)
    if len(cleaned) < min_length or not _NAME_RE.match(cleaned):
        raise ValueError(f"{label} inválido.")
    return cleaned


def validate_email(value: str) -> str:
    cleaned = clean_email(value)
    if not _EMAIL_RE.match(cleaned):
        raise ValueError("Correo electrónico inválido.")
    return cleaned


def validate_optional_email(value: str | None) -> str | None:
    blank_checked = blank_to_none(value) if value is not None else None
    return validate_email(blank_checked) if blank_checked else None


def validate_address(value: str) -> str:
    cleaned = collapse_whitespace(value).upper()
    if len(cleaned) < 5:
        raise ValueError("Dirección del inmueble inválida.")
    return cleaned


def validate_location(value: str) -> str:
    cleaned = clean_name(value)
    if len(cleaned) < 3 or not _LOCATION_RE.match(cleaned):
        raise ValueError("Ubicación inválida.")
    return cleaned


def validate_sector_code(value: str) -> str:
    """Validación deliberadamente laxa (no vacío): no hay certeza del formato
    real de sector_code en producción para imponer un patrón más estricto sin
    arriesgar rechazar códigos válidos."""
    blank_checked = blank_to_none(value)
    if blank_checked is None:
        raise ValueError("Ubicación inválida.")
    return blank_checked


def validate_amount(
    value: object, *, label: str, minimum: int, maximum: int | None = None
) -> int | None:
    """Monto opcional: acepta el string que manda el formulario web
    ("500.000.000", "$ 500000000", "") o un número ya tipado si alguien le
    pega directo a la API con JSON."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} inválido.")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, float):
        amount = round(value)
    else:
        blank_checked = blank_to_none(str(value))
        if blank_checked is None:
            return None
        digits = clean_digits(blank_checked)
        if not digits:
            raise ValueError(f"{label} inválido.")
        amount = int(digits)
    # 0 explícito (típico default de un campo opcional que no llegó del
    # formulario) se trata igual que "en blanco", no como un monto inválido
    # por debajo de `minimum` — mismo criterio que el string vacío arriba.
    if amount == 0:
        return None
    if amount < minimum or (maximum is not None and amount > maximum):
        raise ValueError(f"{label} inválido.")
    return amount


def validate_sale_price(value: object) -> int:
    return validate_amount(value, label="Precio de venta", minimum=1) or 0


def validate_phone(value: str) -> str:
    digits = clean_digits(value)
    if len(digits) < 7:
        raise ValueError("Teléfono inválido.")
    return digits


@dataclass(frozen=True)
class FieldSpec:
    label: str
    hint: str
    kind: str = "text"  # "text" | "select"
    input_type: str = "text"
    required: bool = True
    placeholder: str | None = None
    inputmode: str | None = None
    # Formateo en vivo compartido por page_script_inputs.py (público) y
    # app/interno/page_script.py: None | "uppercase" | "currency" | "lowercase".
    js_format: str | None = None
    suggest: bool = False
    validate: Callable[..., object] | None = None


FIELD_SPECS: dict[str, FieldSpec] = {
    "interested_party": FieldSpec(
        label="Nombre completo del interesado",
        hint="Persona que autoriza la venta del inmueble.",
        placeholder="Ej: Juan Pérez Gómez",
        js_format="uppercase",
        validate=lambda v: validate_person_name(v, label="Nombre completo del interesado"),
    ),
    "email": FieldSpec(
        label="Correo electrónico",
        hint="Correo de contacto del interesado.",
        input_type="email",
        placeholder="Ej: nombre@correo.com",
        js_format="lowercase",
        validate=validate_email,
    ),
    "property_type": FieldSpec(
        label="Tipo de inmueble",
        hint="Categoría del inmueble que se va a autorizar.",
        kind="select",
    ),
    "address": FieldSpec(
        label="Dirección del inmueble",
        hint="Ubicación del inmueble que se va a promocionar.",
        placeholder="Ej: Cra 7 # 12-34, Apto 302",
        js_format="uppercase",
        validate=validate_address,
    ),
    "location": FieldSpec(
        label="Ubicación",
        hint="Sector, ciudad y departamento donde está ubicado el inmueble.",
        placeholder="Ej: El Poblado, Medellín, Antioquia",
        js_format="uppercase",
        suggest=True,
        validate=validate_location,
    ),
    "sale_price": FieldSpec(
        label="Precio de venta (COP)",
        hint="Precio al que te gustaría ofertar el inmueble, en pesos colombianos. No es el precio final de "
        "venta. Puedes dejarlo en blanco si aún no lo tienes claro.",
        required=False,
        placeholder="Ej: $ 350.000.000",
        inputmode="numeric",
        js_format="currency",
        validate=validate_sale_price,
    ),
    "owner_phone": FieldSpec(
        label="Teléfono",
        hint="Número de contacto del propietario.",
        input_type="tel",
        placeholder="Ej: 3001234567",
        validate=validate_phone,
    ),
}
