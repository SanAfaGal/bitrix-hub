"""Payload del formulario interno de creación de lead (ver app/interno/router.py).

Los campos que también existen en el formulario público (`interested_party`,
`email`, `property_type`, `address`, `location`, `sale_price`) usan el mismo
nombre y la misma validación que `BrokerageAuthorizationPayload`
(`app/forms/models.py`) — ambos delegan a `app.shared.field_specs`, así que
una regla de formato solo se escribe una vez. `owner_phone` es propio de
interno: el público no pide teléfono en el formulario (lo trae Bitrix del
contacto ya creado)."""
from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.forms.models import PropertyType
from app.shared.field_specs import (
    PROPERTY_TYPES,
    validate_address,
    validate_location,
    validate_optional_email,
    validate_person_name,
    validate_phone,
    validate_sale_price,
    validate_sector_code,
)


class NuevoLeadPayload(BaseModel):
    """Datos del propietario e inmueble capturados por el captador — lo mínimo
    para crear contacto + deal en Bitrix (`app/flows/interno_nuevo_lead.py`).
    La matrícula NO se pide acá: es obligatoria más adelante, en el paso del
    wizard público que ya la valida en vivo (ver app/forms/router.py) — no
    tiene sentido duplicarla ni volverla opcional acá."""

    interested_party: str
    owner_phone: str
    email: str | None = None
    property_type: PropertyType
    address: str
    location: str
    location_sector_code: str
    sale_price: int = 0
    coverage_override: bool = False
    idempotency_token: str

    @field_validator("interested_party", mode="before")
    @classmethod
    def _validate_interested_party(cls, value: str) -> str:
        return validate_person_name(value, label="Nombre completo del interesado")

    @field_validator("owner_phone", mode="before")
    @classmethod
    def _validate_owner_phone(cls, value: str) -> str:
        return validate_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        return validate_optional_email(value)

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

    @field_validator("sale_price", mode="before")
    @classmethod
    def _validate_sale_price(cls, value: object) -> int:
        return validate_sale_price(value)

    @field_validator("idempotency_token", mode="before")
    @classmethod
    def _validate_idempotency_token(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Falta el token de idempotencia.")
        return value.strip()


PROPERTY_TYPES_FOR_TEMPLATE = PROPERTY_TYPES
