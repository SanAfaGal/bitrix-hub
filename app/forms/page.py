"""Datos del formulario de Autorización de Corretaje — sin HTML.

El HTML/CSS/JS reales viven en `app/forms/jinja_templates/` y
`app/forms/static/{css,js}/`, ensamblados por `app/forms/render.py` (Jinja2).
Este archivo solo arma los datos planos que ese módulo necesita: la lista de
campos (`_FIELDS`/`_LOCATION_FIELD`, a partir de `app.shared.field_specs`,
compartido con `app/interno/`), las secciones visuales y las rutas públicas
del formulario.
"""
from __future__ import annotations

from app.shared.field_specs import FIELD_SPECS, PROPERTY_TYPES

__all__ = [
    "FORM_PATH",
    "TEMPLATE_PATH_URL",
    "CLEAN_SIGNATURE_PATH",
    "VERIFY_MATRICULA_PATH",
    "CONFIRM_MATRICULA_MATCH_PATH",
    "VERIFY_COBERTURA_PATH",
    "ESTADO_SERVICIOS_PATH",
    "FAVICON_URL",
    "LOGO_URL",
    "SECTION_TITLES",
    "SECTION_ICONS",
    "PROPERTY_TYPES",
]


def _shared_field(spec_name: str, **overrides: object) -> dict:
    """Arma un dict de `_FIELDS`/`_LOCATION_FIELD` a partir de `FIELD_SPECS`
    (label/hint/placeholder/kind/input_type/inputmode) — evita que este
    archivo repita a mano el mismo texto que ya vive en
    `app.shared.field_specs`, compartido con `app/interno/`. `overrides`
    puede traer su propio `name` (ej. "location_display", que reusa el texto
    de "location" pero viaja con otro nombre de campo)."""
    spec = FIELD_SPECS[spec_name]
    field = dict(
        name=spec_name,
        label=spec.label,
        hint=spec.hint,
        kind=spec.kind,
        input_type=spec.input_type,
        required=spec.required,
    )
    if spec.placeholder:
        field["placeholder"] = spec.placeholder
    if spec.inputmode:
        field["inputmode"] = spec.inputmode
    field.update(overrides)
    return field


# Rutas públicas: en español y con nombre claro — las abre el cliente final
# desde un link de WhatsApp, tiene que entender qué es antes de tocarlo.
FORM_PATH = "/formularios/autorizacion-de-corretaje"
TEMPLATE_PATH_URL = f"{FORM_PATH}/plantilla.pdf"
CLEAN_SIGNATURE_PATH = f"{FORM_PATH}/limpiar-firma"
VERIFY_MATRICULA_PATH = f"{FORM_PATH}/verify-matricula"
CONFIRM_MATRICULA_MATCH_PATH = f"{FORM_PATH}/confirm-matricula-match"
VERIFY_COBERTURA_PATH = f"{FORM_PATH}/verify-cobertura"
ESTADO_SERVICIOS_PATH = f"{FORM_PATH}/estado-servicios"

# Assets de marca (favicon, logo) — copiados de flash-view, ver app/static/imgs/.
FAVICON_URL = "/static/imgs/favicon.ico"
LOGO_URL = "/static/imgs/logo_short.webp"

# Agrupación visual de los campos en el formulario (no son pasos separados,
# solo subtítulos dentro de la misma página para que se sienta más corto).
SECTION_TITLES = {
    "interested": "Datos del interesado",
    "property": "Datos del inmueble",
    "financial": "Condiciones financieras",
}

# Mismo estilo de ícono (stroke="currentColor") que los botones de
# deshacer/borrar firma más abajo — 24x24, sin relleno.
SECTION_ICONS = {
    "interested": (
        '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>'
        '<circle cx="12" cy="7" r="4"/>'
    ),
    "property": (
        '<path d="M3 9.5 12 3l9 6.5"/>'
        '<path d="M5 10v10h14V10"/>'
    ),
    "financial": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M15 9.5H10.5a1.75 1.75 0 0 0 0 3.5h3a1.75 1.75 0 0 1 0 3.5H9"/>'
        '<path d="M12 7.5v9"/>'
    ),
}

# Campos que ve y llena el cliente. `id_number` se reutiliza para el campo de
# cédula que va junto a la firma (`signer_id_number`), no se pide dos veces.
# `kind` decide cómo se renderiza: "text" -> <input>, "select" -> <select>
# con las opciones de `property_type`, "yesno" -> <select> Sí/No obligatorio.
_FIELDS = [
    _shared_field("interested_party", section="interested"),
    dict(
        name="id_number", label="Documento de identidad", kind="text", input_type="text", required=True,
        section="interested",
        hint="Cédula, cédula de extranjería o pasaporte del interesado, sin puntos ni espacios.",
        placeholder="Ej: 1234567890",
    ),
    _shared_field("email", section="interested"),
    _shared_field("property_type", section="property"),
    # Solo lectura y sin `name`: no vuelve a viajar en el submit (ya viaja el
    # campo real "location", ver _LOCATION_FIELD más abajo) — es nada más
    # para que el cliente vea confirmado acá lo que ya escribió en el wizard,
    # en vez de que el dato "desaparezca" al ocultarse el paso de ubicación.
    _shared_field(
        "location", name="location_display", required=False,
        section="property", readonly=True, no_submit=True,
        confirm_text="Tenemos cobertura en esta zona.",
    ),
    _shared_field("address", section="property"),
    dict(
        name="registration_number", label="Matrícula inmobiliaria", kind="text", input_type="text",
        required=True, section="property",
        hint="Número de identificación del inmueble en el registro de instrumentos públicos.",
        placeholder="Ej: 050-123456",
        confirm_text="Este inmueble no está publicado en Xposure MLS, puedes continuar.",
    ),
    _shared_field("sale_price", section="financial"),
    dict(
        name="mortgage_loan", label="Crédito hipotecario", kind="yesno", required=True,
        section="financial",
        hint="Si el inmueble tiene un crédito hipotecario vigente.",
    ),
    dict(
        name="leasing", label="Leasing", kind="yesno", required=True,
        section="financial",
        hint="Si el inmueble está bajo leasing habitacional.",
    ),
    dict(
        name="outstanding_debt", label="Saldo actual de la deuda (aprox., COP)", kind="text",
        input_type="text", required=False, section="financial", hidden=True,
        hint="Saldo pendiente del crédito hipotecario o leasing, en pesos colombianos. "
        "Puedes dejarlo en blanco si no conoces el monto exacto.",
        placeholder="Ej: $ 50.000.000", inputmode="numeric",
    ),
]

# Ubicación: se pide en el paso de cobertura del wizard (antes del formulario
# completo, ver app/forms/jinja_templates/_wizard_step_location.html), no en
# la sección "Datos del inmueble" — pero es el mismo campo (`name="location"`,
# mismo id, mismo desplegable de sugerencias) así que se renderiza con el
# mismo macro `field()` que el resto (ver `_fields.html`), solo que fuera de
# `_FIELDS`.
_LOCATION_FIELD = _shared_field(
    "location", suggest="location-suggestions", form="authorization-form"
)
