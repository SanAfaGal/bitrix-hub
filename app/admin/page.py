"""Shell del panel admin (topbar, sidebar, editor de plantillas/config) — HTML sueltos
en app/admin/templates/ + app/admin/static/, sigue el patrón de app/interno/.

Cada vista (prospectos, cobertura) sigue armando su propio `body` (como RawHTML) y
llama a `render_app_shell(...)` acá para envolverlo con topbar + head — ver
app/admin/README.md sobre por qué el shell no se duplica por vista."""
from __future__ import annotations

import json
from html import escape
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
from app.shared.staff_nav import staff_fab_html

_TEMPLATES_DIR = Path(__file__).parent / "templates"

FAVICON_URL = "/static/imgs/favicon.ico"
LOGO_URL = "/static/imgs/logo_short.webp"

# Login/logout viven en app/auth/ (cuenta corporativa, único para todo el staff).
LOGOUT_PATH = "/auth/logout"
ADMIN_ROOT_PATH = "/admin"
TEMPLATES_PATH = "/admin/templates"
CONFIG_PATH = "/admin/config"
PROSPECTS_PATH = "/admin/prospects"
COVERAGE_PATH = "/admin/cobertura"

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
}


def _topbar(*, display_name: str, active_view: str) -> str:
    """`display_name` es el nombre real de la cuenta corporativa (`staff_user["name"]`,
    ver `app.auth.deps.require_staff_user`) — no el email que devuelve `require_admin`
    (ese sigue siendo el identificador correcto para auditoría, ej. `updated_by` al
    guardar una plantilla, pero no es lo que se le muestra a la persona). Mismo
    dato/formato ("Sesión iniciada" + inicial) que ya usan `app/interno/` y `app/home/`."""
    def pill(view: str, label: str, href: str, *, has_unsaved_indicator: bool = False) -> str:
        active = " navpill--active" if view == active_view else ""
        dot = '<span class="navpill__dot" data-badge></span>' if has_unsaved_indicator and view == active_view else ""
        icon = _NAVPILL_ICONS.get(view, "")
        return (
            f'<a class="navpill{active}" href="{href}" title="{escape(label)}">'
            f'{icon}<span class="navpill__label">{label}</span>{dot}</a>'
        )

    initial = escape(display_name.strip()[:1].upper() or "?")
    safe_name = escape(display_name)
    return f"""
    <div class="topbar">
      <div class="topbar__brand">
        <img class="topbar__mark" src="{LOGO_URL}" alt="Alberto Álvarez">
        <div class="topbar__identity">
          <span class="topbar__name">Alberto Álvarez</span>
          <span class="topbar__tagline">Panel administrativo</span>
        </div>
      </div>
      <div class="topbar__divider"></div>
      <div class="topbar__nav">
        {pill("templates", "Plantillas", f"{TEMPLATES_PATH}/{_FIRST_TEMPLATE_KEY}", has_unsaved_indicator=True)}
        {pill("config", "Configuración del bot", CONFIG_PATH, has_unsaved_indicator=True)}
        {pill("prospects", "Prospectos", PROSPECTS_PATH)}
        {pill("cobertura", "Cobertura", COVERAGE_PATH)}
      </div>
      <div class="topbar__user">
        <div class="userchip">
          <span class="avatar">{initial}</span>
          <span class="userchip__text">
            <span class="userchip__name">{safe_name}</span>
            <span class="userchip__status">Sesión iniciada</span>
          </span>
          <form method="post" action="{LOGOUT_PATH}">
            <button type="submit" class="logout-btn" aria-label="Cerrar sesión" title="Cerrar sesión">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
    """


def _sidebar(*, selected_key: str) -> str:
    sections_html = []
    for section in TEMPLATE_SECTIONS:
        items_html = []
        for key in section["keys"]:  # type: ignore[index]
            is_active = key == selected_key
            classes = "sidebar__item" + (" sidebar__item--active" if is_active else "")
            dot = '<span class="sidebar__item-dot" data-badge></span>' if is_active else ""
            hint = escape(TEMPLATE_HINTS.get(key, ""))
            items_html.append(
                f'<a class="{classes}" href="{TEMPLATES_PATH}/{escape(key)}">'
                f'<span class="sidebar__item-text">'
                f'<span class="sidebar__item-label">{escape(TEMPLATE_LABELS.get(key, key))}</span>'
                f'<span class="sidebar__item-hint">{hint}</span>'
                f"</span>"
                f'<span class="sidebar__item-end">{dot}'
                f'<svg class="sidebar__item-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" '
                f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                f'<path d="M9 6l6 6-6 6"/></svg></span></a>'
            )
        sections_html.append(
            f'<div class="sidebar__section">'
            f'<div class="sidebar__section-title">{escape(section["name"])}</div>'  # type: ignore[arg-type]
            f'{"".join(items_html)}'
            f"</div>"
        )
    return f"""
    <div class="sidebar">
      <div>
        <div class="sidebar__intro-title">Plantillas</div>
        <div class="sidebar__intro-text">Mensajes reales que le llegan al cliente. Los cambios se aplican al instante.</div>
      </div>
      {"".join(sections_html)}
    </div>
    """


def _var_chips(key: str) -> str:
    variables = TEMPLATE_VARIABLES.get(key, [])
    if not variables:
        return ""
    chips = "".join(
        f'<button type="button" class="var-chip" data-insert-var="{{{{{escape(v)}}}}}">{{{{{escape(v)}}}}}</button>'
        for v in variables
    )
    return f'<div class="var-row"><span class="var-row__label">Insertar variable</span>{chips}</div>'


def render_template_editor_html(
    *, display_name: str, key: str, content: str, flash: str | None = None, flash_error: bool = False
) -> str:
    label = escape(TEMPLATE_LABELS.get(key, key))
    when_used = escape(TEMPLATE_WHEN_USED.get(key, ""))
    samples = json.dumps(TEMPLATE_VARIABLE_SAMPLES.get(key, {}))
    flash_html = ""
    if flash:
        kind = "alert--error" if flash_error else "alert--info"
        flash_html = f'<div class="alert {kind}">{escape(flash)}</div>'

    action_url = RawHTML(f"{TEMPLATES_PATH}/{escape(key)}")
    body = render_template(
        _TEMPLATES_DIR / "template_editor.html",
        label=RawHTML(label),
        when_used=RawHTML(when_used),
        flash_html=RawHTML(flash_html),
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
    flash_html = ""
    if flash:
        kind = "alert--error" if flash_error else "alert--info"
        flash_html = f'<div class="alert {kind}">{escape(flash)}</div>'

    tips = [
        "Se aplica desde el segundo mensaje del cliente en adelante.",
        "Defina el tono (formal o informal), qué datos debe ir pidiendo y en qué orden.",
        "Indique cuándo debe ofrecer pasar la conversación a un asesor humano.",
        "No es un mensaje enviado tal cual — es una instrucción para el asistente.",
    ]
    tips_html = "".join(
        f'<div class="guide-card__tip"><span class="guide-card__tip-dot"></span>'
        f'<p class="guide-card__tip-text">{escape(tip)}</p></div>'
        for tip in tips
    )

    body = render_template(
        _TEMPLATES_DIR / "config.html",
        flash_html=RawHTML(flash_html),
        content=content,
        tips_html=RawHTML(tips_html),
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
