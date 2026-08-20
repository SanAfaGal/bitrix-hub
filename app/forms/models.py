"""Modelo del payload enviado por el formulario de Autorización de Corretaje."""
from __future__ import annotations

from pydantic import BaseModel, Field

# Tope de tamaño para un data URL de imagen en base64. ~10MB de imagen
# decodificada (una foto de celular normal cae muy por debajo de esto); una
# foto en máxima resolución de un celular reciente puede pesar varios MB, así
# que 14M de caracteres da margen sin dejar la puerta abierta a un payload
# gigante pensado para tumbar CPU en la limpieza con OpenCV.
_MAX_IMAGE_DATA_URL_LENGTH = 14_000_000


class BrokerageAuthorizationPayload(BaseModel):
    interested_party: str = ""
    id_number: str = ""
    email: str = ""
    property_type: str = ""
    address: str = ""
    municipality: str = ""
    registration_number: str = ""
    sale_price: str = ""
    mortgage_loan: str = ""
    leasing: str = ""
    outstanding_debt: str = ""
    term_months: str = ""
    signer_id_number: str = ""
    signature_png: str = Field(max_length=_MAX_IMAGE_DATA_URL_LENGTH)
    deal_id: str | None = None


class CleanSignaturePhotoPayload(BaseModel):
    image_png: str = Field(max_length=_MAX_IMAGE_DATA_URL_LENGTH)
