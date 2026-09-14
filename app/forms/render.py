"""Ensambla el HTML del formulario de Autorización de Corretaje vía Jinja2.

Las plantillas viven en `app/forms/jinja_templates/` (HTML real, no strings de
Python) y el CSS/JS en `app/forms/static/{css,js}/` — acá solo se arma el
contexto (datos planos) y se llama `.render()`. El formulario público sigue
siendo una sola respuesta HTTP autocontenida: el CSS/JS no se sirve por
`StaticFiles`, se lee (cacheado, ver `app.shared.static_text.read_static_text`)
y se inyecta inline en `<style>`/`<script>` al renderizar — mismo criterio
que antes de esta migración, solo que la fuente ahora son archivos reales.

`autoescape` de Jinja reemplaza los `html.escape()` manuales que tenía la
versión anterior — todo lo que venga de `prefill`/`deal_id`/`token` pasa por
`{{ }}` normal en las plantillas. Los únicos valores marcados `Markup()` acá
son texto estático controlado por el repo (CSS/JS ya armados, el propio
`window.BH_CONFIG`) — nunca algo derivado de esos parámetros.
"""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment
from markupsafe import Markup

from app.forms.page import (
    CLEAN_SIGNATURE_PATH,
    CONFIRM_MATRICULA_MATCH_PATH,
    ESTADO_SERVICIOS_PATH,
    FAVICON_URL,
    LOGO_URL,
    PROPERTY_TYPES,
    SECTION_ICONS,
    SECTION_TITLES,
    TEMPLATE_PATH_URL,
    VERIFY_COBERTURA_PATH,
    VERIFY_MATRICULA_PATH,
    _FIELDS,
    _LOCATION_FIELD,
)
from app.shared.jinja_env import get_env
from app.shared.static_text import read_static_text

_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"
_CSS_DIR = Path(__file__).parent / "static" / "css"
_JS_DIR = Path(__file__).parent / "static" / "js"

_PROPERTY_TYPE_OPTIONS = [(name, name) for name in PROPERTY_TYPES]


def _env() -> Environment:
    return get_env(str(_TEMPLATES_DIR))


def _css_context() -> dict[str, Markup]:
    return {
        "base_css": Markup(read_static_text(str(_CSS_DIR / "base.css"))),
        "fields_css": Markup(read_static_text(str(_CSS_DIR / "fields.css"))),
        "signature_css": Markup(read_static_text(str(_CSS_DIR / "signature.css"))),
        "wizard_css": Markup(read_static_text(str(_CSS_DIR / "wizard.css"))),
    }


def _build_module_script() -> Markup:
    body = (
        read_static_text(str(_JS_DIR / "_module_header.js"))
        + "\n(function () {\n"
        + read_static_text(str(_JS_DIR / "storage.js"))
        + read_static_text(str(_JS_DIR / "input_formatting.js"))
        + read_static_text(str(_JS_DIR / "signature_model.js"))
        + read_static_text(str(_JS_DIR / "signature_canvas.js"))
        + read_static_text(str(_JS_DIR / "submit_status.js"))
        + read_static_text(str(Path(__file__).parent.parent / "shared" / "static" / "js" / "field_validation.js"))
        + read_static_text(str(_JS_DIR / "submit.js"))
        + "})();\n"
    )
    return Markup(f'<script type="module">\n{body}</script>')


def _build_wizard_script() -> Markup:
    body = (
        "(function () {\n"
        + read_static_text(str(_JS_DIR / "storage.js"))
        + read_static_text(str(_JS_DIR / "wizard_core.js"))
        + read_static_text(str(_JS_DIR / "wizard_matricula.js"))
        + read_static_text(str(_JS_DIR / "wizard_restore.js"))
        + "})();\n"
    )
    return Markup(f"<script>\n{body}</script>")


def _bh_config_script() -> Markup:
    config = {
        "cleanSignaturePath": CLEAN_SIGNATURE_PATH,
        "verifyMatriculaPath": VERIFY_MATRICULA_PATH,
        "confirmMatriculaMatchPath": CONFIRM_MATRICULA_MATCH_PATH,
        "verifyCoberturaPath": VERIFY_COBERTURA_PATH,
        "estadoServiciosPath": ESTADO_SERVICIOS_PATH,
    }
    payload = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    return Markup(f"<script>window.BH_CONFIG = {payload};</script>")


def _location_prefill_script(location_prefill: dict[str, str] | None) -> Markup:
    if not location_prefill:
        return Markup("")
    payload = json.dumps(location_prefill, ensure_ascii=False).replace("</", "<\\/")
    return Markup(f"<script>window.__BH_LOCATION_PREFILL__ = {payload};</script>")


def _fields_with_prefill(prefill: dict[str, str] | None) -> list[dict]:
    prefill = prefill or {}
    fields = []
    for f in _FIELDS:
        value = prefill.get(f["name"])
        fields.append({**f, "value": value} if value else f)
    return fields


def render_form_html(
    deal_id: str | None = None,
    token: str | None = None,
    prefill: dict[str, str] | None = None,
    location_prefill: dict[str, str] | None = None,
) -> str:
    """`prefill` solo cubre campos que no dependen de un paso del wizard con
    verificación en vivo (`property_type`, `address`, `sale_price`) — no
    `registration_number`, que necesita pasar por su chequeo de duplicado en
    Xposure para quedar en el estado "confirmado" que espera el wizard (ver
    `_FIELDS`/`confirm_text`). El cliente los ve prellenados pero editables —
    puede corregir un dato mal capturado.

    `location_prefill` (`{"location": ..., "sector_code": ...}`) sí se salta
    el paso del wizard en vez de solo prellenarlo: el sector ya pasó por
    cobertura cuando el captador creó el lead (ver `app.forms.router`), así
    que no tiene sentido volver a pedirle al cliente que lo confirme."""
    context = {
        "favicon_url": FAVICON_URL,
        "logo_url": LOGO_URL,
        "template_path_url": TEMPLATE_PATH_URL,
        "deal_id": deal_id,
        "token": token,
        "fields": _fields_with_prefill(prefill),
        "location_field": _LOCATION_FIELD,
        "property_type_options": _PROPERTY_TYPE_OPTIONS,
        "section_titles": SECTION_TITLES,
        "section_icons": {key: Markup(value) for key, value in SECTION_ICONS.items()},
        "bh_config_script": _bh_config_script(),
        "location_prefill_script": _location_prefill_script(location_prefill),
        "module_script": _build_module_script(),
        "wizard_script": _build_wizard_script(),
        **_css_context(),
    }
    return _env().get_template("form.html").render(**context)


def _render_message_page(*, icon: str, title: str, message: str) -> str:
    context = {
        "icon": icon,
        "title": title,
        "message": message,
        "favicon_url": FAVICON_URL,
        "logo_url": LOGO_URL,
        **{k: v for k, v in _css_context().items() if k != "wizard_css"},
    }
    return _env().get_template("message.html").render(**context)


def render_link_invalid_html() -> str:
    return _render_message_page(
        icon="⚠",
        title="Enlace no válido",
        message="Este enlace no es válido. Pídele a tu asesor que te comparta uno nuevo.",
    )


def render_already_signed_html() -> str:
    return _render_message_page(
        icon="✓",
        title="Autorización ya firmada",
        message=(
            "Esta autorización ya fue firmada. Si necesitas hacer algún cambio, "
            "contacta a tu asesor."
        ),
    )
