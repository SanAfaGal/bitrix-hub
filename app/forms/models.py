"""Modelo del payload enviado por el formulario de Autorización de Corretaje."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.forms.cleaning import blank_to_none, clean_id_number, clean_uppercase_alnum
from app.shared.field_specs import (
    PROPERTY_TYPES,
    PropertyType,
    validate_address,
    validate_amount,
    validate_email,
    validate_location,
    validate_person_name,
    validate_sale_price,
    validate_sector_code,
)

# Tope de tamaño para un data URL de imagen en base64. ~10MB de imagen
# decodificada (una foto de celular normal cae muy por debajo de esto); una
# foto en máxima resolución de un celular reciente puede pesar varios MB, así
# que 14M de caracteres da margen sin dejar la puerta abierta a un payload
# gigante pensado para tumbar CPU en la limpieza con OpenCV.
_MAX_IMAGE_DATA_URL_LENGTH = 14_000_000

YesNo = Literal["si", "no"]

# Matrícula inmobiliaria: "código de oficina - número de matrícula" (ej.
# "50C-1945945"), código de oficina de 3-4 caracteres (dígitos con letra
# opcional al final) y número de matrícula de 5-8 dígitos; o solo dígitos
# para el formato viejo sin separador. Misma regla que `MATRICULA_PATTERN`
# en app/flows/registry_duplicate_check.py.
_REGISTRATION_NUMBER_RE = re.compile(r"^(?:\d{3}[A-Z]?|\d{2}[A-Z])-\d{5,8}$|^\d{4,10}$")
# Letras, números y guion — cédula, cédula de extranjería o pasaporte (puede
# traer letras); el guion se permite porque en varios países es parte real
# del número, no solo formato (ver clean_id_number).
_ID_NUMBER_RE = re.compile(r"^[A-Z0-9-]+$")


def _clean_and_check_id_number(value: str, *, field_label: str) -> str:
    cleaned = clean_id_number(value)
    if not (5 <= len(cleaned) <= 20) or not _ID_NUMBER_RE.match(cleaned):
        raise ValueError(f"{field_label} inválido.")
    return cleaned


def validate_registration_number(value: str) -> str:
    """Compartido entre `BrokerageAuthorizationPayload` y `VerifyRegistrationNumberPayload`
    (chequeo en vivo del wizard, ver app/forms/router.py) — mismo formato en los dos casos."""
    blank_checked = blank_to_none(value)
    if blank_checked is None:
        raise ValueError("Matrícula inmobiliaria inválida.")
    cleaned = clean_uppercase_alnum(blank_checked)
    if not _REGISTRATION_NUMBER_RE.match(cleaned):
        raise ValueError("Matrícula inmobiliaria inválida.")
    return cleaned


def _clean_optional_amount(
    value: object, *, field_label: str, minimum: int, maximum: int | None = None
) -> int | None:
    return validate_amount(value, label=field_label, minimum=minimum, maximum=maximum)


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
    location: str
    location_sector_code: str
    registration_number: str
    sale_price: int = 0
    mortgage_loan: YesNo
    leasing: YesNo
    outstanding_debt: int = 0
    # Ya no se le pide al cliente en el formulario — queda fijo en 6 meses.
    term_months: int = 6
    signer_id_number: str
    signature_png: str = Field(max_length=_MAX_IMAGE_DATA_URL_LENGTH)
    deal_id: str | None = None
    token: str | None = None

    @field_validator("interested_party", mode="before")
    @classmethod
    def _validate_interested_party(cls, value: str) -> str:
        return validate_person_name(value, label="Nombre completo del interesado")

    @field_validator("id_number", "signer_id_number", mode="before")
    @classmethod
    def _validate_id_number(cls, value: str) -> str:
        return _clean_and_check_id_number(value, field_label="Documento de identidad")

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("address", mode="before")
    @classmethod
    def _validate_address(cls, value: str) -> str:
        return validate_address(value)

    @field_validator("location", mode="before")
    @classmethod
    def _validate_location(cls, value: str) -> str:
        return validate_location(value)

    @field_validator("location_sector_code", mode="before")
    @classmethod
    def _validate_location_sector_code(cls, value: str) -> str:
        return validate_sector_code(value)

    @field_validator("registration_number", mode="before")
    @classmethod
    def _validate_registration_number(cls, value: str) -> str:
        return validate_registration_number(value)

    @field_validator("sale_price", mode="before")
    @classmethod
    def _validate_sale_price(cls, value: object) -> int:
        # Opcional en el formulario: en blanco se guarda como 0 en vez de
        # quedar vacío, para no dejar el campo sin dato en Bitrix.
        return validate_sale_price(value)

    @field_validator("outstanding_debt", mode="before")
    @classmethod
    def _validate_outstanding_debt(cls, value: object) -> int:
        return _clean_optional_amount(value, field_label="Saldo actual de la deuda", minimum=0) or 0


class CleanSignaturePhotoPayload(BaseModel):
    image_png: str = Field(max_length=_MAX_IMAGE_DATA_URL_LENGTH)


class VerifyRegistrationNumberPayload(BaseModel):
    """Body del chequeo en vivo de matrícula (paso de excepción del wizard, ver app/forms/router.py)."""

    registration_number: str
    deal_id: str | None = None
    token: str | None = None

    @field_validator("registration_number", mode="before")
    @classmethod
    def _validate_registration_number(cls, value: str) -> str:
        return validate_registration_number(value)


class VerifyLocationCoveragePayload(BaseModel):
    """Body del chequeo en vivo de cobertura (paso del wizard, ver app/forms/router.py)."""

    sector_code: str
    deal_id: str | None = None
    token: str | None = None

    @field_validator("sector_code", mode="before")
    @classmethod
    def _validate_sector_code(cls, value: str) -> str:
        return validate_sector_code(value)


class ConfirmMatriculaMatchPayload(BaseModel):
    """Body de la respuesta del cliente a "¿es este tu inmueble?" (ver app/forms/router.py)."""

    registration_number: str
    url: str | None = None
    confirmed: bool
    deal_id: str | None = None
    token: str | None = None

    @field_validator("registration_number", mode="before")
    @classmethod
    def _validate_registration_number(cls, value: str) -> str:
        return validate_registration_number(value)
