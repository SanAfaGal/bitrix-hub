"""Modelo del payload enviado por el formulario de Autorización de Corretaje."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.forms.cleaning import (
    blank_to_none,
    clean_digits,
    clean_email,
    clean_id_number,
    clean_name,
    clean_uppercase_alnum,
    collapse_whitespace,
)

# Tope de tamaño para un data URL de imagen en base64. ~10MB de imagen
# decodificada (una foto de celular normal cae muy por debajo de esto); una
# foto en máxima resolución de un celular reciente puede pesar varios MB, así
# que 14M de caracteres da margen sin dejar la puerta abierta a un payload
# gigante pensado para tumbar CPU en la limpieza con OpenCV.
_MAX_IMAGE_DATA_URL_LENGTH = 14_000_000

# Opciones del campo Bitrix UF_CRM_1773860139420 ("Tipo de inmueble"): se
# guarda el NAME tal como lo usa `filler.py` para el PDF. Los VALUE numéricos
# de Bitrix no se usan todavía (no hay sync de vuelta a ese campo UF).
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
YesNo = Literal["si", "no"]

_NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-\s]+$")
# Dominio hecho de etiquetas separadas por un solo punto (sin puntos dobles,
# sin punto al inicio/final del dominio) y TLD de al menos 2 letras — más
# estricto que "algo@algo.algo" (que dejaba pasar "juan@example..com" o
# "juan@example.c").
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@.]+(\.[^\s@.]+)*\.[a-zA-Z]{2,}$")
# Solo números y guion — la matrícula inmobiliaria no lleva letras.
_REGISTRATION_NUMBER_RE = re.compile(r"^[0-9-]+$")
# Letras, números y guion — cédula, cédula de extranjería o pasaporte (puede
# traer letras); el guion se permite porque en varios países es parte real
# del número, no solo formato (ver clean_id_number).
_ID_NUMBER_RE = re.compile(r"^[A-Z0-9-]+$")


def _clean_and_check_name(value: str, *, field_label: str, min_length: int) -> str:
    cleaned = clean_name(value)
    if len(cleaned) < min_length or not _NAME_RE.match(cleaned):
        raise ValueError(f"{field_label} inválido.")
    return cleaned


def _clean_and_check_id_number(value: str, *, field_label: str) -> str:
    cleaned = clean_id_number(value)
    if not (5 <= len(cleaned) <= 20) or not _ID_NUMBER_RE.match(cleaned):
        raise ValueError(f"{field_label} inválido.")
    return cleaned


def _clean_optional_amount(
    value: object, *, field_label: str, minimum: int, maximum: int | None = None
) -> int | None:
    """Monto/cantidad opcional: acepta el string que manda el formulario web
    ("500.000.000", "$ 500000000", "") o un número ya tipado si alguien le
    pega directo a la API con JSON — en los dos casos se valida el mismo
    rango, no solo cuando llega como string."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_label} inválido.")
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
            raise ValueError(f"{field_label} inválido.")
        amount = int(digits)
    if amount < minimum or (maximum is not None and amount > maximum):
        raise ValueError(f"{field_label} inválido.")
    return amount


class BrokerageAuthorizationPayload(BaseModel):
    # Sin default: que falte la clave en el payload debe rechazarse igual que
    # si llegara vacía — mismo criterio para todos los campos obligatorios
    # (property_type/mortgage_loan/leasing ya lo tenían; ver nota en
    # `_validate_*` de por qué un default "" se saltaba el validator).
    interested_party: str
    id_number: str
    email: str
    property_type: PropertyType
    address: str
    municipality: str
    registration_number: str
    sale_price: int = 0
    mortgage_loan: YesNo
    leasing: YesNo
    outstanding_debt: int = 0
    term_months: int = 3
    signer_id_number: str
    signature_png: str = Field(max_length=_MAX_IMAGE_DATA_URL_LENGTH)
    deal_id: str | None = None
    token: str | None = None

    @field_validator("interested_party", mode="before")
    @classmethod
    def _validate_interested_party(cls, value: str) -> str:
        return _clean_and_check_name(value, field_label="Nombre completo del interesado", min_length=3)

    @field_validator("id_number", "signer_id_number", mode="before")
    @classmethod
    def _validate_id_number(cls, value: str) -> str:
        return _clean_and_check_id_number(value, field_label="Documento de identidad")

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        cleaned = clean_email(value)
        if not _EMAIL_RE.match(cleaned):
            raise ValueError("Correo electrónico inválido.")
        return cleaned

    @field_validator("address", mode="before")
    @classmethod
    def _validate_address(cls, value: str) -> str:
        cleaned = collapse_whitespace(value).upper()
        if len(cleaned) < 5:
            raise ValueError("Dirección del inmueble inválida.")
        return cleaned

    @field_validator("municipality", mode="before")
    @classmethod
    def _validate_municipality(cls, value: str) -> str:
        return _clean_and_check_name(value, field_label="Municipio", min_length=3)

    @field_validator("registration_number", mode="before")
    @classmethod
    def _validate_registration_number(cls, value: str) -> str:
        blank_checked = blank_to_none(value)
        if blank_checked is None:
            raise ValueError("Matrícula inmobiliaria inválida.")
        cleaned = clean_uppercase_alnum(blank_checked)
        if not _REGISTRATION_NUMBER_RE.match(cleaned):
            raise ValueError("Matrícula inmobiliaria inválida.")
        return cleaned

    @field_validator("sale_price", mode="before")
    @classmethod
    def _validate_sale_price(cls, value: object) -> int | None:
        return _clean_optional_amount(value, field_label="Precio de venta", minimum=1)

    @field_validator("outstanding_debt", mode="before")
    @classmethod
    def _validate_outstanding_debt(cls, value: object) -> int | None:
        return _clean_optional_amount(value, field_label="Saldo actual de la deuda", minimum=0)

    @field_validator("term_months", mode="before")
    @classmethod
    def _validate_term_months(cls, value: object) -> int | None:
        # Tope en 99 (no 120): el blanco "(__)" de la plantilla solo tiene
        # espacio físico para 2 dígitos (ver app/forms/filler.py).
        return _clean_optional_amount(value, field_label="Duración del acuerdo", minimum=1, maximum=99)


class CleanSignaturePhotoPayload(BaseModel):
    image_png: str = Field(max_length=_MAX_IMAGE_DATA_URL_LENGTH)
