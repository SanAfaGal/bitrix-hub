"""`Environment` de Jinja2 cacheado por directorio de plantillas.

Cada paquete (`app/forms/`, `app/admin/`, `app/interno/`, `app/home/`) arma
sus fragmentos de HTML con macros/plantillas propias en su propio
`html_templates/` (o `templates/`) — este helper evita repetir la
construcción del `Environment` (mismo `autoescape`/`trim_blocks`/
`lstrip_blocks` en todos), sin acoplar los paquetes entre sí: cada uno sigue
siendo dueño de sus propias plantillas.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


@lru_cache(maxsize=None)
def get_env(templates_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
