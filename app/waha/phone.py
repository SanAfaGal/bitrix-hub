"""Limpieza del teléfono guardado en Bitrix y su transformación al formato
que espera Waha (chatId de WhatsApp).

Bitrix guarda el teléfono de un contacto en el campo `PHONE`, una lista de
entradas `{"VALUE": "...", "VALUE_TYPE": "..."}` — nunca un string simple —
y el valor casi siempre viene "sucio": con espacios, guiones, paréntesis,
con o sin `+57` adelante. Este módulo concentra esa limpieza en un solo
lugar para que cualquier flujo que necesite mandar un WhatsApp no tenga que
reinventarla.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_COUNTRY_CODE = "57"  # Colombia — la mayoría de números en Bitrix son locales, de 10 dígitos.

# Tipos de teléfono de Bitrix, en orden de preferencia para notificar por WhatsApp.
_PREFERRED_PHONE_TYPES = ("MOBILE", "WORK", "HOME", "OTHER")


def extract_phone_from_contact(contact: dict[str, Any]) -> str | None:
    """Extrae el mejor teléfono disponible del campo PHONE de un contacto de Bitrix.

    Prefiere MOBILE si hay varios números; si no, toma el primero que haya.
    Retorna None si el contacto no tiene ningún teléfono.
    """
    phones = contact.get("PHONE")
    if not isinstance(phones, list) or not phones:
        return None

    by_type: dict[str, str] = {}
    for entry in phones:
        if not isinstance(entry, dict):
            continue
        value = entry.get("VALUE")
        value_type = entry.get("VALUE_TYPE")
        if isinstance(value, str) and value.strip():
            by_type.setdefault(value_type, value)

    for preferred_type in _PREFERRED_PHONE_TYPES:
        if preferred_type in by_type:
            return by_type[preferred_type]

    return next(iter(by_type.values()), None)


def to_chat_id(raw_phone: str, default_country_code: str = DEFAULT_COUNTRY_CODE) -> str | None:
    """Limpia un teléfono de Bitrix y lo convierte al chatId que espera Waha.

    Acepta formatos como "300 111 2233", "+57 (300) 111-2233" o
    "0057 300 1112233". Si el número no trae indicador de país (+ o 00), se
    asume local y se le antepone `default_country_code`. Retorna None si el
    resultado no parece un número válido — no adivina de más.
    """
    if not raw_phone or not raw_phone.strip():
        return None

    cleaned = raw_phone.strip()
    has_country_code = cleaned.startswith("+") or cleaned.startswith("00")
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]

    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return None

    if not has_country_code:
        if len(digits) == 10:
            digits = default_country_code + digits
        elif len(digits) < 11:
            logger.warning("Teléfono sin código de país y longitud ambigua: %s", raw_phone)
            return None

    if not (10 <= len(digits) <= 15):
        logger.warning("Teléfono con longitud inválida tras limpiar: %s -> %s", raw_phone, digits)
        return None

    return f"{digits}@c.us"
