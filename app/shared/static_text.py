"""Lee archivos estáticos (CSS/JS) como texto crudo, cacheado por proceso.

Generaliza el patrón de cacheo de `app/shared/html_templates.py::_read_template`
para contenido que no lleva placeholders — se usa tal cual, concatenado o
inyectado directamente en la página final (ver `app/forms/render.py`).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def read_static_text(path: str) -> str:
    """El archivo no cambia en runtime — se lee una sola vez por proceso."""
    return Path(path).read_text(encoding="utf-8")
