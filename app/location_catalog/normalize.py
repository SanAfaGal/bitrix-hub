"""Normalización del texto de ubicación mostrado en la UI.

Puerto de la lógica ya probada en
`Procesos-Automatizacion-Bitrix/scripts/listar_valores_campo_sector_zona_ciudad.py`
(`normalize`, `clean_descripcion`, `dedupe_all`) — ese script resolvía el
mismo problema (sector/zona/ciudad/departamento con partes repetidas y
formato inconsistente) sobre un campo de Bitrix ya parseado a 5 niveles; acá
no hace falta el parseo (`split_descripcion`/`assign_fields`), porque
`cat_mobilia_sectores` ya trae sector/zona/ciudad/departamento como columnas
separadas — solo se reutiliza la limpieza de formato y el dedup.
"""
from __future__ import annotations

import re
import unicodedata

# Artículos/preposiciones que van en minúscula salvo que sean la primera
# palabra del campo (ej. "Ciudad del Rio", pero "La Estrella" sí lleva
# mayúscula por ir de primero).
_LOWERCASE_WORDS = {"de", "del", "la", "el", "los", "las", "y", "a"}


def normalize_key(value: str) -> str:
    """Texto normalizado para comparar/deduplicar: trim, minúsculas, sin acentos."""
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def clean_location_part(text: str) -> str:
    """Limpia y normaliza el formato de una parte de la ubicación (sector, zona, ciudad o departamento).

    - Colapsa espacios dobles/extra, sin espacios al inicio/final.
    - Primera letra de cada palabra en mayúscula, resto en minúscula, salvo
      artículos/preposiciones que no sean la primera palabra.
    - Mayúscula tras punto (ej. "D.c." -> "D.C" solo si viniera así de la fuente).
    """
    text = re.sub(r"\s+", " ", text.strip())
    words = []
    for index, word in enumerate(text.split(" ")):
        if index > 0 and normalize_key(word) in _LOWERCASE_WORDS:
            words.append(word.lower())
        else:
            words.append(word.capitalize())
    text = " ".join(words).strip()
    return re.sub(r"\.(\s*)([a-záéíóúñ])", lambda m: "." + m.group(1) + m.group(2).upper(), text)


def _strip_trailing_word_block(text: str, remove_key: str) -> str:
    """Quita de `text` el bloque de palabras `remove_key` (ya normalizada,
    puede ser de varias palabras, ej. "norte de santander") SOLO si está
    pegado al final del texto — nunca en medio ni al inicio.

    Sector/zona a veces repiten el nombre de la ciudad o el departamento
    como sufijo (ej. sector "San Gabriel Itagui" con ciudad "Itagui", o
    sector "IPIALES NARIÑO" con ciudad "Ipiales" y departamento "Nariño") —
    error de datos de la fuente, no del código. Pero un nombre de ciudad
    puede además ser el prefijo de un nombre de sector completamente
    distinto (ej. sector "San Pedro de los Milagros" con ciudad "San
    pedro"): ahí NO hay que tocarlo, porque no es relleno, es un nombre
    propio más largo. Por eso solo se quita cuando coincide justo con las
    últimas palabras del texto (lo que queda pegado a la coma en el
    resultado final), nunca como coincidencia al inicio o en medio.
    """
    if not remove_key:
        return text
    words = text.split()
    remove_words = remove_key.split()
    window = len(remove_words)
    if window == 0 or window > len(words):
        return text
    if normalize_key(" ".join(words[-window:])) != remove_key:
        return text
    return " ".join(words[:-window])


def dedupe_parts(parts: list[str]) -> list[str]:
    """Quita partes repetidas (comparadas normalizadas), quedándose con la
    ÚLTIMA aparición de cada una (no la primera).

    sector/zona a veces repiten el nombre del departamento como relleno
    cuando ese sector no tiene una subdivisión propia — ej. sector_code
    41013 en cat_mobilia_sectores: sector="HUILA", zona="Huila",
    ciudad="Neiva", departamento="Huila" (ciudad y departamento ya vienen
    bien puestos, el problema es el relleno en sector/zona). Con "conservar
    la primera" ese relleno se adelanta y el resultado queda "Huila, Neiva"
    (departamento antes que ciudad); quedándose con la última aparición, el
    departamento real (al final) se queda con el cupo y el resultado es
    "Neiva, Huila" — orden correcto, sin tocar sector/zona/ciudad/departamento
    como campos independientes.
    """
    keys = [normalize_key(part) for part in parts]
    last_index_by_key: dict[str, int] = {}
    for index, key in enumerate(keys):
        if key:
            last_index_by_key[key] = index
    return [part for index, (part, key) in enumerate(zip(parts, keys)) if key and last_index_by_key[key] == index]


def build_location_label(sector: str, zona: str, ciudad: str, departamento: str, pais: str) -> str:
    """Arma el texto de ubicación mostrado en la UI: cada parte limpia y sin repetidos, unidas por coma."""
    for remove_key in (normalize_key(ciudad or ""), normalize_key(departamento or ""), normalize_key(pais or "")):
        if sector:
            sector = _strip_trailing_word_block(sector, remove_key)
        if zona:
            zona = _strip_trailing_word_block(zona, remove_key)

    cleaned = [
        clean_location_part(part) for part in (sector, zona, ciudad, departamento, pais) if part and part.strip()
    ]
    return ", ".join(dedupe_parts(cleaned))
