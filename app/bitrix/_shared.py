"""Helpers internos compartidos entre los mixins de `BitrixClient` (`client_*.py`).

Privado del paquete — nada fuera de `app/bitrix/` debe importar de acá.
"""
from __future__ import annotations

REQUEST_TIMEOUT = 10


class BitrixLookupError(Exception):
    """Interna: una búsqueda (no una creación) falló por red/HTTP. Nunca sale de este paquete."""


def normalize_person_name(name: str | None) -> str | None:
    """Normaliza un nombre de persona a "Cada Palabra Así" antes de guardarlo en Bitrix.

    Independiente de dónde venga el nombre (WhatsApp, formulario web, lo
    que sea) — Bitrix no debe terminar con "DIANA HERRERA" ni "diana
    herrera", siempre con la primera letra de cada palabra en mayúscula y
    el resto en minúscula.
    """
    if not name or not name.strip():
        return name
    return " ".join(word.capitalize() for word in name.split())


def error_detail(exc: Exception) -> str:
    """Extrae el cuerpo de la respuesta de un HTTPError, si lo hay — Bitrix manda el motivo real ahí.

    `raise_for_status()` lanza antes de poder leer el body, así que sin esto
    un 400 de Bitrix se loguea sin decir *qué* campo rechazó.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        return f" | respuesta Bitrix: {response.json()}"
    except ValueError:
        return f" | respuesta Bitrix: {response.text}"
