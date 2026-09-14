"""Shell del panel admin (topbar, sidebar, editor de plantillas/config) — HTML sueltos
en app/admin/templates/ + app/admin/static/, sigue el patrón de app/interno/.

Cada vista (prospectos, cobertura) sigue armando su propio `body` (como RawHTML) y
llama a `render_app_shell(...)` acá para envolverlo con topbar + head — ver
app/admin/README.md sobre por qué el shell no se duplica por vista."""
from __future__ import annotations

import json
from pathlib import Path

from app.message_templates.store import (
    TEMPLATE_HINTS,
    TEMPLATE_LABELS,
    TEMPLATE_SECTIONS,
    TEMPLATE_VARIABLE_SAMPLES,
    TEMPLATE_VARIABLES,
    TEMPLATE_WHEN_USED,
)
from app.shared.html_templates import RawHTML, render_template
from app.shared.jinja_env import get_env
from app.shared.staff_nav import staff_fab_html

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_JINJA_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"


def _fragments():
    return get_env(str(_JINJA_TEMPLATES_DIR)).get_template("_shell_fragments.html").module

FAVICON_URL = "/static/imgs/favicon.ico"
LOGO_URL = "/static/imgs/logo_short.webp"

# Login/logout viven en app/auth/ (cuenta corporativa, único para todo el staff).
LOGOUT_PATH = "/auth/logout"
ADMIN_ROOT_PATH = "/admin"
TEMPLATES_PATH = "/admin/templates"
CONFIG_PATH = "/admin/config"
PROSPECTS_PATH = "/admin/prospects"
COVERAGE_PATH = "/admin/cobertura"
WHATSAPP_PATH = "/admin/whatsapp"

_FIRST_TEMPLATE_KEY = TEMPLATE_SECTIONS[0]["keys"][0]  # type: ignore[index]


_NAVPILL_ICONS = {
    "templates": (
        '<svg class="navpill__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
    ),
    "config": (
        '<svg class="navpill__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 '
        '1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 '
        '1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 '
        '9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 '
        '2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 '
        '0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
    ),
    "prospects": (
        '<svg class="navpill__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
        '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
    ),
    "cobertura": (
        '<svg class="navpill__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>'
    ),
    "whatsapp": (
        '<svg class="navpill__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>'
    ),
}


def _topbar(*, display_name: str, active_view: str) -> str:
    """`display_name` es el nombre real de la cuenta corporativa (`staff_user["name"]`,
    ver `app.auth.deps.require_staff_user`) — no el email que devuelve `require_admin`
    (ese sigue siendo el identificador correcto para auditoría, ej. `updated_by` al
    guardar una plantilla, pero no es lo que se le muestra a la persona). Mismo
    dato/formato ("Sesión iniciada" + inicial) que ya usan `app/interno/` y `app/home/`."""
    pills = [
        ("templates", "Plantillas", f"{TEMPLATES_PATH}/{_FIRST_TEMPLATE_KEY}", _NAVPILL_ICONS["templates"], True),
        ("config", "Configuración del bot", CONFIG_PATH, _NAVPILL_ICONS["config"], True),
        ("prospects", "Prospectos", PROSPECTS_PATH, _NAVPILL_ICONS["prospects"], False),
        ("cobertura", "Cobertura", COVERAGE_PATH, _NAVPILL_ICONS["cobertura"], False),
        ("whatsapp", "WhatsApp", WHATSAPP_PATH, _NAVPILL_ICONS["whatsapp"], False),
    ]
    initial = display_name.strip()[:1].upper() or "?"
    return _fragments().topbar(display_name, initial, active_view, LOGO_URL, LOGOUT_PATH, pills)


def _sidebar(*, selected_key: str) -> str:
    sections = [
        {
            "name": section["name"],  # type: ignore[index]
            "entries": [
                {
                    "key": key,
                    "label": TEMPLATE_LABELS.get(key, key),
                    "hint": TEMPLATE_HINTS.get(key, ""),
                    "active": key == selected_key,
                }
                for key in section["keys"]  # type: ignore[index]
            ],
        }
        for section in TEMPLATE_SECTIONS
    ]
    return _fragments().sidebar(sections, TEMPLATES_PATH)


def _var_chips(key: str) -> str:
    tokens = ["{{" + v + "}}" for v in TEMPLATE_VARIABLES.get(key, [])]
    return _fragments().var_chips(tokens)


def render_template_editor_html(
    *, display_name: str, key: str, content: str, flash: str | None = None, flash_error: bool = False
) -> str:
    label = TEMPLATE_LABELS.get(key, key)
    when_used = TEMPLATE_WHEN_USED.get(key, "")
    samples = json.dumps(TEMPLATE_VARIABLE_SAMPLES.get(key, {}))

    action_url = RawHTML(f"{TEMPLATES_PATH}/{key}")
    body = render_template(
        _TEMPLATES_DIR / "template_editor.html",
        label=label,
        when_used=when_used,
        flash_html=RawHTML(_fragments().flash(flash, flash_error)),
        action_url=action_url,
        restore_url=RawHTML(f"{action_url}/restore"),
        var_chips_html=RawHTML(_var_chips(key)),
        samples=RawHTML(samples),
        content=content,
    )
    return render_app_shell(
        display_name=display_name, active_view="templates", title="Plantillas de WhatsApp", sidebar=_sidebar(selected_key=key), body=body
    )


def render_config_html(*, display_name: str, content: str, flash: str | None = None, flash_error: bool = False) -> str:
    tips = [
        "Se aplica desde el segundo mensaje del cliente en adelante.",
        "Defina el tono (formal o informal), qué datos debe ir pidiendo y en qué orden.",
        "Indique cuándo debe ofrecer pasar la conversación a un asesor humano.",
        "No es un mensaje enviado tal cual — es una instrucción para el asistente.",
    ]

    body = render_template(
        _TEMPLATES_DIR / "config.html",
        flash_html=RawHTML(_fragments().flash(flash, flash_error)),
        content=content,
        tips_html=RawHTML(_fragments().tips(tips)),
    )
    return render_app_shell(display_name=display_name, active_view="config", title="Configuración del bot", sidebar="", body=body)


def render_app_shell(
    *,
    display_name: str,
    active_view: str,
    title: str,
    sidebar: str,
    body: str,
    extra_head_html: str = "",
    extra_body_html: str = "",
) -> str:
    """`extra_head_html`/`extra_body_html` son ganchos aditivos (default vacío) para que una
    vista agregue su propio `<link rel="stylesheet">`/`<script>` sin tocar el shell — usado
    por prospects_page.py para prospects.css/prospects.js, ver render_prospects_html."""
    return render_template(
        _TEMPLATES_DIR / "shell.html",
        title=title,
        topbar=RawHTML(_topbar(display_name=display_name, active_view=active_view)),
        sidebar=RawHTML(sidebar),
        body=RawHTML(body),
        extra_head_html=RawHTML(extra_head_html),
        extra_body_html=RawHTML(extra_body_html),
        staff_fab_html=RawHTML(staff_fab_html(active="admin", is_admin=True)),
    )
