"""HTML autocontenido del formulario de Autorización de Corretaje (sin dependencias externas).

El CSS y el JS viven aparte (`page_styles.py`, `page_script.py`) — este
archivo solo arma el esqueleto HTML y los datos de los campos, para no pasar
las ~500 líneas por archivo.
"""
from __future__ import annotations

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

# Campos de texto que ve y llena el cliente. `id_number` se reutiliza para el
# campo de cédula que va junto a la firma (`signer_id_number`), no se pide dos veces.
_TEXT_FIELDS = [
    ("interested_party", "Nombre completo del interesado", "text", True),
    ("id_number", "Cédula (CC)", "text", True),
    ("email", "Correo electrónico", "email", True),
    ("property_type", "Tipo de inmueble", "text", True),
    ("address", "Dirección del inmueble", "text", True),
    ("municipality", "Municipio", "text", True),
    ("registration_number", "Matrícula inmobiliaria", "text", True),
    ("sale_price", "Precio de venta ($)", "text", True),
    ("mortgage_loan", "Crédito hipotecario (si aplica)", "text", False),
    ("leasing", "Leasing (si aplica)", "text", False),
    ("outstanding_debt", "Saldo actual de la deuda ($, aprox.)", "text", False),
    ("term_months", "Duración del acuerdo (meses)", "text", True),
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
      <form id="authorization-form">
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
            <div class="signature-placeholder signature-placeholder--hidden" id="signature-placeholder">
              Tocá para elegir una foto de tu firma
            </div>
          </div>
          <input type="file" id="signature-file" accept="image/*" class="signature-file-input">
          <div class="signature-actions">
            <span class="signature-status-text" id="signature-status-text">Firma aquí con el dedo</span>
            <span class="signature-actions__buttons">
              <button type="button" class="btn btn--outline" id="undo-signature">Deshacer</button>
              <button type="button" class="btn btn--outline" id="clear-signature">Borrar</button>
            </span>
          </div>
          <p class="signature-note">La fecha de la firma se coloca automáticamente al enviar la autorización.</p>
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


def render_form_html() -> str:
    fields_html = "\n".join(
        '        <div class="field">\n'
        '          <label class="field__label" for="field-{name}">{label}</label>\n'
        '          <input class="field__input" id="field-{name}" type="{input_type}" '
        'name="{name}"{required}>\n'
        "        </div>".format(
            label=label,
            input_type=input_type,
            name=name,
            required=" required" if required else "",
        )
        for name, label, input_type, required in _TEXT_FIELDS
    )
    return (
        _HTML.replace("__FIELDS_HTML__", fields_html)
        .replace("__TEMPLATE_PATH_URL__", TEMPLATE_PATH_URL)
        .replace("__FAVICON_URL__", FAVICON_URL)
        .replace("__LOGO_URL__", LOGO_URL)
        .replace("__STYLE__", FORM_STYLE)
        .replace("__SCRIPT__", FORM_SCRIPT.replace("__CLEAN_SIGNATURE_PATH__", CLEAN_SIGNATURE_PATH))
    )
