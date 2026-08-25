"""Transforma un teléfono ya extraído del CRM al formato que espera Waha
(chatId de WhatsApp).

El teléfono llega "sucio": con espacios, guiones, paréntesis, con o sin
`+57` adelante — sin importar de qué CRM viene, la limpieza es la misma.
Este módulo concentra esa limpieza en un solo lugar para que cualquier
flujo que necesite mandar un WhatsApp no tenga que reinventarla. Extraer
el teléfono crudo de la forma de contacto de cada CRM es responsabilidad
del cliente de ese CRM (`CrmClient.get_contact_phone`), no de este módulo.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_COUNTRY_CODE = "57"  # Colombia — la mayoría de contactos son números locales, de 10 dígitos.


def to_chat_id(raw_phone: str, default_country_code: str = DEFAULT_COUNTRY_CODE) -> str | None:
    """Limpia un teléfono y lo convierte al chatId que espera Waha.

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


def from_chat_id(chat_id: str) -> str | None:
    """Extrae el teléfono (con código de país, sin `+`) de un chatId de Waha.

    Inverso de `to_chat_id`: `"573001112233@c.us"` -> `"573001112233"`.
    Retorna `None` si `chat_id` no tiene la forma esperada (ej. un chat de
    grupo, que termina en `@g.us` en vez de `@c.us`).
    """
    if not chat_id or "@" not in chat_id:
        return None

    digits, _, suffix = chat_id.partition("@")
    if suffix != "c.us" or not digits.isdigit():
        return None

    return digits


def lid_from_chat_id(chat_id: str) -> str | None:
    """Extrae el identificador `@lid` de un chatId, cuando el remitente ocultó su número.

    WhatsApp permite ocultar el número de teléfono (username/privacidad); en
    ese caso Waha manda el chat como `"<id opaco>@lid"` en vez de
    `"<teléfono>@c.us"`. Ese identificador **no es un teléfono** — es un ID
    interno de WhatsApp, estable para un mismo remitente pero inútil para
    buscar por teléfono en el CRM. Retorna `None` si `chat_id` no es un chat
    `@lid` (ej. es `@c.us` o `@g.us`, o viene vacío).
    """
    if not chat_id or "@" not in chat_id:
        return None

    identifier, _, suffix = chat_id.partition("@")
    if suffix != "lid" or not identifier:
        return None

    return identifier
