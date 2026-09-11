"""Payload del formulario interno de creación de lead (ver app/interno/router.py)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.forms.cleaning import clean_digits, clean_email, clean_name, collapse_whitespace
from app.forms.models import PROPERTY_TYPES, PropertyType, validate_sector_code


def _validate_phone(value: str) -> str:
    digits = clean_digits(value)
    if len(digits) < 7:
        raise ValueError("Teléfono inválido.")
    return digits


class NuevoLeadPayload(BaseModel):
    """Datos del propietario e inmueble capturados por el captador — lo mínimo
    para crear contacto + deal en Bitrix (`app/flows/interno_nuevo_lead.py`).
    La matrícula NO se pide acá: es obligatoria más adelante, en el paso del
    wizard público que ya la valida en vivo (ver app/forms/router.py) — no
    tiene sentido duplicarla ni volverla opcional acá."""

    owner_full_name: str
    owner_phone: str
    owner_email: str | None = None
    property_type: PropertyType
    address: str
    location: str
    location_sector_code: str
    expected_sale_price: int = 0
    coverage_override: bool = False
    idempotency_token: str

    @field_validator("owner_full_name", mode="before")
    @classmethod
    def _validate_owner_full_name(cls, value: str) -> str:
        cleaned = clean_name(value)
        if len(cleaned) < 3:
            raise ValueError("Nombre completo del propietario inválido.")
        return cleaned

    @field_validator("owner_phone", mode="before")
    @classmethod
    def _validate_owner_phone(cls, value: str) -> str:
        return _validate_phone(value)

    @field_validator("owner_email", mode="before")
    @classmethod
    def _validate_owner_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return clean_email(value)

    @field_validator("address", mode="before")
    @classmethod
    def _validate_address(cls, value: str) -> str:
        cleaned = collapse_whitespace(value).upper()
        if len(cleaned) < 5:
            raise ValueError("Dirección del inmueble inválida.")
        return cleaned

    @field_validator("location", mode="before")
    @classmethod
    def _validate_location(cls, value: str) -> str:
        cleaned = clean_name(value)
        if len(cleaned) < 3:
            raise ValueError("Ubicación inválida.")
        return cleaned

    @field_validator("location_sector_code", mode="before")
    @classmethod
    def _validate_location_sector_code(cls, value: str) -> str:
        return validate_sector_code(value)

    @field_validator("expected_sale_price", mode="before")
    @classmethod
    def _validate_expected_sale_price(cls, value: object) -> int:
        if value is None or value == "":
            return 0
        digits = clean_digits(str(value))
        return int(digits) if digits else 0

    @field_validator("idempotency_token", mode="before")
    @classmethod
    def _validate_idempotency_token(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Falta el token de idempotencia.")
        return value.strip()


PROPERTY_TYPES_FOR_TEMPLATE = PROPERTY_TYPES
