"""Sirve archivos `.html` sueltos con placeholders, sin Jinja2 ni build step.

Para páginas donde interesa más el resaltado de sintaxis/autocompletado real
del editor que tener el marcado como función pura de Python (a diferencia de
`app/forms/page.py`, que arma el HTML como string en `.py` — ver la discusión
de trade-offs en el diseño de app/interno/). Reemplazo de placeholders vía
`.replace()` simple, con `html.escape()` sobre cada valor — mismo nivel de
seguridad que el enfoque actual, sin agregar Jinja2 como dependencia nueva.
"""
from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path


class RawHTML(str):
    """Marca un valor como HTML ya seguro (armado por el propio código, nunca a
    partir de input de usuario sin escapar) — `render_template` lo inserta tal
    cual, sin pasar por `html.escape()` de nuevo. Para fragmentos como
    `flash_html`/opciones de un `<select>`, construidos por el backend."""


@lru_cache(maxsize=None)
def _read_template(path: str) -> str:
    """El archivo no cambia en runtime — se lee una sola vez por proceso."""
    return Path(path).read_text(encoding="utf-8")


def render_template(path: str | Path, **values: str | RawHTML) -> str:
    """Reemplaza `{{clave}}` por el valor de `values` — escapado con `html.escape()`,
    salvo que el valor sea `RawHTML` (fragmento de marcado ya armado por el backend).

    Un placeholder que quede sin reemplazar en el archivo (typo, o falta pasar
    el valor) se deja tal cual — no lanza, para no tumbar la página por un
    error de plantilla; revisar visualmente alcanza para detectarlo.
    """
    content = _read_template(str(path))
    for key, value in values.items():
        replacement = value if isinstance(value, RawHTML) else escape(str(value))
        content = content.replace(f"{{{{{key}}}}}", replacement)
    return content
