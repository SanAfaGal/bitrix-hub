"""Modelos de datos del cliente de Xposure y de la API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PropertySearchResult(BaseModel):
    """Resultado de la búsqueda de un inmueble por número de matrícula."""

    tax_roll: str = Field(description="Número de matrícula (tax roll) consultado.", examples=["5322493"])
    exists: bool = Field(description="True si Xposure encontró el inmueble.")
    mls: str | None = Field(default=None, description="Número MLS del inmueble, si existe.", examples=["238899"])
    url: str | None = Field(
        default=None,
        description="Link al detalle del inmueble en Xposure, si existe.",
        examples=["https://tu-dominio-xposure.com/portal/colombia/ViewDetail?mlsForDisplay=238899"],
    )
    reason: str | None = Field(
        default=None,
        description="Motivo cuando no se encontró resultado, o cuando se encontró pero no se pudo extraer el MLS.",
        examples=["No se encontraron resultados"],
    )


class BulkRequest(BaseModel):
    """Cuerpo de la petición para consultar varias matrículas a la vez."""

    tax_rolls: list[str] = Field(
        min_length=1,
        description="Lista de números de matrícula a consultar, en orden.",
        examples=[["5322493", "5322494"]],
    )
