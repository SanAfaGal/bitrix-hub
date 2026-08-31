"""HTML autocontenido del panel admin (sin dependencias externas) — sigue el patrón de app/forms/page.py."""
from __future__ import annotations

import json
from html import escape

from app.admin.page_script import EDITOR_SCRIPT
from app.admin.page_styles import ADMIN_STYLE
from app.message_templates.store import (
    TEMPLATE_HINTS,
    TEMPLATE_LABELS,
    TEMPLATE_SECTIONS,
    TEMPLATE_VARIABLE_SAMPLES,
    TEMPLATE_VARIABLES,
    TEMPLATE_WHEN_USED,
)

FAVICON_URL = "/static/imgs/favicon.ico"
LOGO_URL = "/static/imgs/logo_short.webp"

LOGIN_PATH = "/admin/login"
LOGOUT_PATH = "/admin/logout"
TEMPLATES_PATH = "/admin/templates"
CONFIG_PATH = "/admin/config"

_FIRST_TEMPLATE_KEY = TEMPLATE_SECTIONS[0]["keys"][0]  # type: ignore[index]


def _head(title: str) -> str:
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} — Alberto Álvarez</title>
<link rel="icon" href="{FAVICON_URL}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700&display=swap" rel="stylesheet">
{ADMIN_STYLE}"""


def render_login_html(*, error: str | None = None) -> str:
    error_html = f'<div class="alert alert--error">{escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="es">
<head>
{_head("Iniciar sesión")}
</head>
<body>
<div class="page">
  <div class="frame">
    <div class="brand">
      <img class="brand__logo" src="{LOGO_URL}" alt="Alberto Álvarez">
      <div class="brand__identity">
        <span class="brand__name">Alberto Álvarez</span>
        <span class="brand__tagline">Panel del bot de WhatsApp</span>
      </div>
    </div>
    <div class="card">
      <div class="card__header">
        <h1 class="card__title">Iniciar sesión</h1>
        <p class="card__subtitle">Acceso del equipo comercial al panel de plantillas del bot.</p>
      </div>
      {error_html}
      <form method="post" action="{LOGIN_PATH}" style="display:flex;flex-direction:column;gap:var(--space-4)">
        <div class="field">
          <label class="field__label" for="username">Usuario</label>
          <input class="field__input" id="username" name="username" type="text" required autofocus>
        </div>
        <div class="field">
          <label class="field__label" for="password">Clave</label>
          <input class="field__input" id="password" name="password" type="password" required>
        </div>
        <button type="submit" class="btn btn--primary">Entrar</button>
      </form>
    </div>
  </div>
</div>
</body>
</html>
"""


def _topbar(*, username: str, active_view: str) -> str:
    def pill(view: str, label: str, href: str) -> str:
        active = " navpill--active" if view == active_view else ""
        dot = '<span class="navpill__dot" data-badge></span>' if view == active_view else ""
        return f'<a class="navpill{active}" href="{href}">{label}{dot}</a>'

    return f"""
    <div class="topbar">
      <div class="topbar__brand">
        <div class="topbar__mark">AA</div>
        <div class="topbar__identity">
          <span class="topbar__name">Alberto Álvarez</span>
          <span class="topbar__tagline">Panel del bot de WhatsApp</span>
        </div>
      </div>
      <div class="topbar__divider"></div>
      <div class="topbar__nav">
        {pill("templates", "Plantillas", f"{TEMPLATES_PATH}/{_FIRST_TEMPLATE_KEY}")}
        {pill("config", "Configuración del bot", CONFIG_PATH)}
      </div>
      <div class="topbar__user">
        <div class="userchip">
          <span class="avatar">{escape(username[:2].upper())}</span>
          {escape(username)}
        </div>
        <form method="post" action="{LOGOUT_PATH}">
          <button type="submit" class="logout-btn">Cerrar sesión</button>
        </form>
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
    *, username: str, key: str, content: str, flash: str | None = None, flash_error: bool = False
) -> str:
    label = escape(TEMPLATE_LABELS.get(key, key))
    when_used = escape(TEMPLATE_WHEN_USED.get(key, ""))
    samples = json.dumps(TEMPLATE_VARIABLE_SAMPLES.get(key, {}))
    flash_html = ""
    if flash:
        kind = "alert--error" if flash_error else "alert--info"
        flash_html = f'<div class="alert {kind}">{escape(flash)}</div>'

    body = f"""
    <div class="content">
      <div style="display:flex;flex-direction:column;gap:6px;">
        <div class="content__title-row">
          <h1 class="content__title">{label}</h1>
          <span class="badge-unsaved" data-badge>Sin guardar</span>
        </div>
        <p class="content__desc">{when_used}</p>
      </div>
      {flash_html}
      <div class="editor-grid">
        <div class="editor-col">
          <form method="post" action="{TEMPLATES_PATH}/{escape(key)}" style="display:flex;flex-direction:column;gap:var(--space-3)">
            {_var_chips(key)}
            <div class="editor-wrap">
              <textarea class="editor-textarea" name="content" rows="11" data-editor data-var-samples='{samples}'>{escape(content)}</textarea>
              <span class="char-count" data-char-count></span>
            </div>
            <div class="btn-row">
              <button type="submit" class="btn btn--primary">Guardar</button>
              <button type="submit" formaction="{TEMPLATES_PATH}/{escape(key)}/restore" class="btn btn--outline">Restaurar valor por defecto</button>
              <span class="save-meta">Guardado</span>
            </div>
          </form>
        </div>
        <div class="side-col">
          <div>
            <div class="preview-label">Así lo ve el cliente</div>
            <div class="chat-frame">
              <div class="chat-bubble">
                <div class="chat-bubble__text" data-preview-text>{escape(content)}</div>
                <div class="chat-bubble__meta">
                  <span class="chat-bubble__time">9:41 a. m.</span>
                  <svg width="14" height="10" viewBox="0 0 16 11" fill="none"><path d="M1 5.5L4.5 9L11 1.5" stroke="#53bdeb" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 5.5L8.5 9L15 1.5" stroke="#53bdeb" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    """
    return _app_shell(username=username, active_view="templates", sidebar=_sidebar(selected_key=key), body=body)


def render_config_html(*, username: str, content: str, flash: str | None = None, flash_error: bool = False) -> str:
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

    body = f"""
    <div class="content content--config">
      <div style="display:flex;flex-direction:column;gap:6px;">
        <div class="content__title-row">
          <h1 class="content__title">Configuración del bot</h1>
          <span class="badge-unsaved" data-badge>Sin guardar</span>
        </div>
        <p class="content__desc">Cómo se comporta el asistente en el resto de la conversación — no es un mensaje fijo, sino instrucciones que el bot sigue para responder.</p>
      </div>
      {flash_html}
      <div class="editor-grid">
        <div class="editor-col">
          <form method="post" action="{CONFIG_PATH}" style="display:flex;flex-direction:column;gap:var(--space-3)">
            <div class="editor-wrap">
              <textarea class="editor-textarea" name="content" rows="16" data-editor data-var-samples='{{}}'>{escape(content)}</textarea>
              <span class="char-count" data-char-count></span>
            </div>
            <div class="btn-row">
              <button type="submit" class="btn btn--primary">Guardar</button>
              <button type="submit" formaction="{CONFIG_PATH}/restore" class="btn btn--outline">Restaurar valor por defecto</button>
              <span class="save-meta">Guardado</span>
            </div>
          </form>
        </div>
        <div class="side-col">
          <div class="guide-card">
            <div class="guide-card__title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0c688e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
              Guía rápida
            </div>
            {tips_html}
          </div>
          <div class="info-card">
            <span class="info-card__label">Cuándo se usa</span>
            <p class="info-card__text">Se aplica desde el segundo mensaje del cliente en adelante — el primer mensaje siempre lo manda una de las plantillas de bienvenida, sin pasar por acá.</p>
          </div>
        </div>
      </div>
    </div>
    """
    return _app_shell(username=username, active_view="config", sidebar="", body=body)


def _app_shell(*, username: str, active_view: str, sidebar: str, body: str) -> str:
    title = "Configuración del bot" if active_view == "config" else "Plantillas de WhatsApp"
    return f"""<!doctype html>
<html lang="es">
<head>
{_head(title)}
</head>
<body>
<div class="page-outer">
<div class="app">
  {_topbar(username=username, active_view=active_view)}
  <div class="body">
    {sidebar}
    {body}
  </div>
</div>
</div>
{EDITOR_SCRIPT}
</body>
</html>
"""
