"""Países disponibles para el indicativo del teléfono del formulario interno
(`app/interno/`) — el público no pide teléfono en su formulario, así que
esto no es un `FieldSpec` más en `app/shared/field_specs.py`, es su propia
lista.

La lista completa (~245 países) sale de `phonenumbers` (indicativo de
llamada, el mismo dataset de libphonenumber que usan Twilio/WhatsApp) y
`babel` (nombre en español) — nada hardcodeado a mano, así que un país nuevo
o un cambio de indicativo lo trae la próxima actualización de esas
librerías, no un edit acá. Colombia es el default: la mayoría de leads son
locales y `app/waha/phone.py::to_chat_id` ya asume Colombia para un número
de 10 dígitos sin indicativo.
"""
from __future__ import annotations

import phonenumbers
from babel import Locale

DEFAULT_PHONE_COUNTRY_CODE = "57"
DEFAULT_PHONE_COUNTRY_ISO2 = "co"

# Región "001" = servicios no geográficos (satelital, UPT, etc. — ver
# `phonenumbers.COUNTRY_CODE_TO_REGION_CODE`), no un país real que alguien
# vaya a elegir acá.
_NON_GEOGRAPHIC_REGION = "001"


def _build_phone_countries() -> tuple[dict[str, str], ...]:
    locale = Locale("es")
    rows = []
    for calling_code, regions in phonenumbers.COUNTRY_CODE_TO_REGION_CODE.items():
        for region in regions:
            if region == _NON_GEOGRAPHIC_REGION:
                continue
            name = locale.territories.get(region)
            if not name:
                continue
            rows.append({"iso2": region.lower(), "code": str(calling_code), "name": name})
    # Colombia primero (default del formulario), el resto alfabético por
    # nombre en español — así el desplegable no obliga a buscar Colombia
    # entre 245 opciones cada vez.
    rows.sort(key=lambda row: (row["iso2"] != DEFAULT_PHONE_COUNTRY_ISO2, row["name"]))
    return tuple(rows)


PHONE_COUNTRIES: tuple[dict[str, str], ...] = _build_phone_countries()


def phone_country_by_code(code: str) -> dict[str, str]:
    """El primer país que use ese indicativo (varios países pueden compartir
    uno, ej. +1) — o Colombia si no está en la lista (código desconocido o
    manipulado a mano en el POST)."""
    for country in PHONE_COUNTRIES:
        if country["code"] == code:
            return country
    return PHONE_COUNTRIES[0]
