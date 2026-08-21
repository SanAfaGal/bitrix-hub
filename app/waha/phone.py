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
