"""Funciones de limpieza reutilizadas por los validators de `models.py`.

Puras (sin efectos secundarios) para que sean fáciles de testear por separado
de la validación de formato que hace Pydantic.
"""
from __future__ import annotations

import re


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def clean_name(value: str) -> str:
    """Trim + espacios colapsados + MAYÚSCULAS (todo el formulario va en mayúscula, salvo el correo)."""
    return collapse_whitespace(value).upper()


def clean_digits(value: str) -> str:
    """Deja solo los dígitos (quita puntos, espacios, guiones, $, etc.)."""
    return re.sub(r"\D", "", value)


def clean_email(value: str) -> str:
    return value.strip().lower()


def clean_uppercase_alnum(value: str) -> str:
    """Trim + mayúsculas + sin espacios internos (para matrícula inmobiliaria)."""
    return re.sub(r"\s+", "", value.strip().upper())


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
