"""HTML autocontenido del formulario de Autorización de Corretaje (sin dependencias externas).

El CSS y el JS viven aparte (`page_styles.py`, `page_script.py`) — este
archivo solo arma el esqueleto HTML y los datos de los campos, para no pasar
las ~500 líneas por archivo.
"""
from __future__ import annotations

from html import escape

from app.forms.models import PROPERTY_TYPES
from app.forms.page_script import FORM_SCRIPT
from app.forms.page_styles import FORM_STYLE

# Rutas públicas: en español y con nombre claro — las abre el cliente final
# desde un link de WhatsApp, tiene que entender qué es antes de tocarlo.
FORM_PATH = "/formularios/autorizacion-de-corretaje"
TEMPLATE_PATH_URL = f"{FORM_PATH}/plantilla.pdf"
CLEAN_SIGNATURE_PATH = f"{FORM_PATH}/limpiar-firma"

# Assets de marca (favicon, logo) — copiados de flash-view, ver app/static/imgs/.
FAVICON_URL = "/static/imgs/favicon.ico"
LOGO_URL = "/static/imgs/logo_short.webp"

# Campos que ve y llena el cliente. `id_number` se reutiliza para el campo de
# cédula que va junto a la firma (`signer_id_number`), no se pide dos veces.
# `kind` decide cómo se renderiza: "text" -> <input>, "select" -> <select>
# con las opciones de `property_type`, "yesno" -> <select> Sí/No obligatorio.
_FIELDS = [
    dict(
        name="interested_party", label="Nombre completo del interesado", kind="text",
        input_type="text", required=True,
        hint="Escríbelo completo, tal como aparece en tu cédula.",
        placeholder="Ej: Juan Pérez Gómez",
    ),
    dict(
        name="id_number", label="Cédula (CC)", kind="text", input_type="text", required=True,
        hint="Solo números, sin puntos ni espacios.",
        placeholder="Ej: 1234567890", inputmode="numeric",
    ),
    dict(
        name="email", label="Correo electrónico", kind="text", input_type="email", required=True,
        hint="Un correo donde te podamos contactar.",
        placeholder="Ej: nombre@correo.com",
    ),
    dict(
        name="property_type", label="Tipo de inmueble", kind="select", required=True,
        hint="Selecciona el tipo de inmueble que vas a autorizar.",
    ),
    dict(
        name="address", label="Dirección del inmueble", kind="text", input_type="text", required=True,
        hint="Incluye número, apartamento o detalles que ayuden a ubicarlo.",
        placeholder="Ej: Cra 7 # 12-34, Apto 302",
    ),
    dict(
        name="municipality", label="Municipio", kind="text", input_type="text", required=True,
        hint="Municipio donde está ubicado el inmueble.",
        placeholder="Ej: Envigado",
    ),
    dict(
        name="registration_number", label="Matrícula inmobiliaria", kind="text", input_type="text",
        required=False,
        hint="Solo números y guion. Déjala en blanco si no la tienes.",
        placeholder="Ej: 050-123456",
    ),
    dict(
        name="sale_price", label="Precio de venta ($)", kind="text", input_type="text", required=False,
        hint="Valor aproximado, en pesos colombianos. Déjalo en blanco si no aplica.",
        placeholder="Ej: $ 350.000.000", inputmode="numeric",
    ),
    dict(
        name="mortgage_loan", label="Crédito hipotecario", kind="yesno", required=True,
        hint="Indica si el inmueble tiene un crédito hipotecario vigente.",
    ),
    dict(
        name="leasing", label="Leasing", kind="yesno", required=True,
        hint="Indica si el inmueble está bajo leasing habitacional.",
    ),
    dict(
        name="outstanding_debt", label="Saldo actual de la deuda ($, aprox.)", kind="text",
        input_type="text", required=False,
        hint="Saldo aproximado de la deuda. Déjalo en blanco si no aplica.",
        placeholder="Ej: $ 50.000.000", inputmode="numeric",
    ),
    dict(
        name="term_months", label="Duración del acuerdo (meses)", kind="text", input_type="text",
        required=False,
        hint="Tiempo en meses que Alberto Álvarez administrará el inmueble. Déjalo en blanco si no aplica.",
        placeholder="Ej: 12", inputmode="numeric",
    ),
]

_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autorización de Corretaje — Alberto Álvarez</title>
<link rel="icon" href="__FAVICON_URL__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700&display=swap" rel="stylesheet">
__STYLE__
</head>
<body>
<div class="page">
  <div class="frame">
    <div class="brand">
      <img class="brand__logo" src="__LOGO_URL__" alt="Alberto Álvarez">
      <span class="brand__name">Alberto Álvarez</span>
      <span class="brand__tagline">Servicios Integrales Inmobiliarios</span>
    </div>
    <div class="card">
      <div class="card__header">
        <h1 class="card__title">Autorización de Corretaje Inmobiliario</h1>
        <p class="card__subtitle">Antes de llenar tus datos, lee el documento completo.</p>
      </div>
      <a class="document-cta" href="__TEMPLATE_PATH_URL__" target="_blank" rel="noopener">
        <span class="document-cta__icon">📄</span>
        <span class="document-cta__text">
          <strong>Ver documento completo</strong>
          <span>Autorización de Corretaje — PDF</span>
        </span>
        <span class="document-cta__arrow">›</span>
      </a>
    </div>
    <div class="card">
      <div class="card__header">
        <h2 class="card__title">Completa tus datos</h2>
        <p class="card__subtitle">Llena tus datos y firma al final.</p>
      </div>
      <form id="authorization-form" novalidate>
__DEAL_ID_FIELD__
__FIELDS_HTML__
        <div class="field-group">
          <div class="signature-group__header">
            <span class="field-group__legend">Firma del interesado</span>
            <div class="signature-tabs">
              <button type="button" class="signature-tab signature-tab--active" id="tab-draw">Dibujar</button>
              <button type="button" class="signature-tab" id="tab-upload">Subir foto</button>
            </div>
          </div>
          <div class="signature-canvas-wrap">
            <canvas id="signature-canvas" class="signature-box"></canvas>
            <div class="signature-toolbar">
              <button type="button" class="signature-icon-btn" id="undo-signature" aria-label="Deshacer último trazo" title="Deshacer">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M9 14 4 9l5-5"/>
                  <path d="M4 9h10.5A5.5 5.5 0 0 1 20 14.5v0A5.5 5.5 0 0 1 14.5 20H11"/>
                </svg>
              </button>
              <button type="button" class="signature-icon-btn" id="clear-signature" aria-label="Borrar firma" title="Borrar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                  <path d="M10 11v6"/>
                  <path d="M14 11v6"/>
                  <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </div>
            <div class="signature-placeholder signature-placeholder--hidden" id="signature-placeholder">
              Toca para elegir una foto de tu firma
            </div>
            <div class="signature-processing-overlay signature-processing-overlay--hidden" id="signature-processing-overlay">
              <span class="spinner spinner--lg"></span>
              <span class="signature-processing-overlay__text" id="signature-processing-overlay-text">Limpiando la firma...</span>
            </div>
          </div>
          <input type="file" id="signature-file" accept="image/*" class="signature-file-input">
          <div class="signature-actions">
            <span class="signature-status-text" id="signature-status-text">Firma aquí con el dedo</span>
          </div>
        </div>
        <button type="submit" class="btn btn--primary" id="submit-button">Enviar autorización</button>
        <div id="form-status"></div>
      </form>
    </div>
  </div>
</div>
__SCRIPT__
</body>
</html>
"""


def _render_text_input(field: dict) -> str:
    placeholder = field.get("placeholder")
    return (
        '          <input class="field__input" id="field-{name}" type="{input_type}" '
        'name="{name}"{placeholder}{inputmode}{required}>'.format(
            name=field["name"],
            input_type=field["input_type"],
            placeholder=f' placeholder="{escape(placeholder)}"' if placeholder else "",
            inputmode=f' inputmode="{field["inputmode"]}"' if field.get("inputmode") else "",
            required=" required" if field["required"] else "",
        )
    )


def _render_select(field: dict, options: list[tuple[str, str]]) -> str:
    options_html = "\n".join(
        f'            <option value="{escape(value)}">{escape(label)}</option>' for value, label in options
    )
    return (
        f'          <select class="field__input" id="field-{field["name"]}" name="{field["name"]}"'
        f'{" required" if field["required"] else ""}>\n'
        '            <option value="" selected disabled>Selecciona una opción...</option>\n'
        f"{options_html}\n"
        "          </select>"
    )


def _render_field(field: dict) -> str:
    if field["kind"] == "select":
        body = _render_select(field, [(name, name) for name in PROPERTY_TYPES])
    elif field["kind"] == "yesno":
        body = _render_select(field, [("si", "Sí"), ("no", "No")])
    else:
        body = _render_text_input(field)
    required_mark = ' <span class="field__required">*</span>' if field["required"] else ""
    return (
        '        <div class="field">\n'
        f'          <label class="field__label" for="field-{field["name"]}">'
        f"{escape(field['label'])}{required_mark}</label>\n"
        f'          <span class="field__hint">{escape(field["hint"])}</span>\n'
        f"{body}\n"
        f'          <span class="field__error" id="error-{field["name"]}"></span>\n'
        "        </div>"
    )


def render_form_html(deal_id: str | None = None) -> str:
    deal_id_field_html = (
        f'        <input type="hidden" name="deal_id" value="{escape(deal_id)}">' if deal_id else ""
    )
    fields_html = "\n".join(_render_field(field) for field in _FIELDS)
    return (
        _HTML.replace("__DEAL_ID_FIELD__", deal_id_field_html)
        .replace("__FIELDS_HTML__", fields_html)
        .replace("__TEMPLATE_PATH_URL__", TEMPLATE_PATH_URL)
        .replace("__FAVICON_URL__", FAVICON_URL)
        .replace("__LOGO_URL__", LOGO_URL)
        .replace("__STYLE__", FORM_STYLE)
        .replace("__SCRIPT__", FORM_SCRIPT.replace("__CLEAN_SIGNATURE_PATH__", CLEAN_SIGNATURE_PATH))
    )
