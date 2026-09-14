"""JS genérico para marcar errores de campo y validar obligatorios.

Compartido por `app/forms/` (formulario público, lo inyecta inline) y
`app/interno/` (formulario interno, lo carga como `<script src>` — ver
`app/interno/templates/nuevo_lead.html`) — cada uno lo concatena/carga dentro
de su propia IIFE, después de declarar `form`
(`document.getElementById(...)` / `document.querySelector(...)`), y asume la
misma convención de marcado: cada campo obligatorio vive en un `.field` que
contiene el `.field__input` y, opcionalmente, un `.field__error` donde cae
el mensaje (ver `.field__error`/`.field__error--visible` en
`app/forms/static/css/fields.css` y `app/interno/static/estilos.css`).

Contenido real en `app/shared/static/js/field_validation.js`, servido
también por `StaticFiles` en `/static/shared/js/field_validation.js` — acá
solo se lee y cachea, para que `app/forms/` lo siga inyectando inline.
"""
from __future__ import annotations

from pathlib import Path

from app.shared.static_text import read_static_text

FIELD_VALIDATION_SCRIPT = read_static_text(str(Path(__file__).parent / "static" / "js" / "field_validation.js"))
