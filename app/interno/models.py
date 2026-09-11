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

from app.crm.protocol import SOURCE_CHANNELS
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
from app.shared.phone_countries import DEFAULT_PHONE_COUNTRY_CODE, phone_country_by_code


class NuevoLeadPayload(BaseModel):
    """Datos del propietario e inmueble capturados por el captador — lo mínimo
    para crear contacto + deal en Bitrix (`app/flows/interno_nuevo_lead.py`).
    La matrícula NO se pide acá: es obligatoria más adelante, en el paso del
    wizard público que ya la valida en vivo (ver app/forms/router.py) — no
    tiene sentido duplicarla ni volverla opcional acá."""

    interested_party: str
    owner_phone: str
    phone_country_code: str = DEFAULT_PHONE_COUNTRY_CODE
    email: str | None = None
    property_type: PropertyType
    address: str
    location: str
    location_sector_code: str
    sale_price: int = 0
    source_channel: str
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

    @field_validator("phone_country_code", mode="before")
    @classmethod
    def _validate_phone_country_code(cls, value: str) -> str:
        # No hay forma de mandar un indicativo "inválido" desde el
        # desplegable (son valores fijos de app/shared/phone_countries.py) —
        # esto solo cubre a alguien pegándole directo a la API con un
        # indicativo que no está en la lista, cae a Colombia en vez de fallar.
        return phone_country_by_code(str(value).strip())["code"]

    @property
    def full_phone(self) -> str:
        """Teléfono con indicativo de país listo para Bitrix — Colombia se
        deja sin indicativo (`app/waha/phone.py::to_chat_id` ya lo asume
        para un número de 10 dígitos), los demás países sí lo llevan."""
        if self.phone_country_code == DEFAULT_PHONE_COUNTRY_CODE:
            return self.owner_phone
        return f"{self.phone_country_code}{self.owner_phone}"

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

    @field_validator("source_channel", mode="before")
    @classmethod
    def _validate_source_channel(cls, value: str) -> str:
        valid = {identifier for identifier, _ in SOURCE_CHANNELS}
        if value not in valid:
            raise ValueError("Selecciona un canal de origen.")
        return value

    @field_validator("idempotency_token", mode="before")
    @classmethod
    def _validate_idempotency_token(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Falta el token de idempotencia.")
        return value.strip()


PROPERTY_TYPES_FOR_TEMPLATE = PROPERTY_TYPES
