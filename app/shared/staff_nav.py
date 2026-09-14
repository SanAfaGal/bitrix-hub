"""Botón flotante (esquina inferior derecha) para moverse entre las páginas
del staff (Inicio / Crear lead / Admin) sin tocar el header de cada página.

Autocontenido a propósito (marcado + `<style>` propio, con clases prefijadas
`staff-fab`, en `app/shared/jinja_templates/staff_fab.html`) — así se puede
insertar en `app/home/`, `app/interno/` y `app/admin/` sin depender de
ninguno de sus sistemas de estilos (`estilos.css` vs. el CSS de
`app/admin/static/`), sin editarlos y sin riesgo de que un cambio ahí rompa
el resto del diseño de la página. Usa `<details>/<summary>` para el menú
desplegable — sin JavaScript.
"""
from __future__ import annotations

from pathlib import Path

from app.shared.html_templates import RawHTML
from app.shared.jinja_env import get_env

_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"

_MENU_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>'
    "</svg>"
)
_HOME_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'
    "</svg>"
)
_LEAD_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/>'
    "</svg>"
)
_ADMIN_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
    "</svg>"
)

_LINKS: tuple[tuple[str, str, str, str], ...] = (
    ("home", "/", "Inicio", _HOME_ICON),
    ("lead", "/interno/nuevo-lead", "Crear lead", _LEAD_ICON),
    ("admin", "/admin", "Panel admin", _ADMIN_ICON),
)


def staff_fab_html(*, active: str, is_admin: bool) -> RawHTML:
    """`active` es uno de "home"/"lead"/"admin" — resalta el enlace de la página
    actual. El enlace a Admin no se renderiza para quien no está en
    `ADMIN_EMAILS` (entrar a `/admin` sin permiso ya da 403 vía `require_admin`,
    no hace falta ofrecer un enlace que no lleva a nada)."""
    links = [link for link in _LINKS if link[0] != "admin" or is_admin]
    env = get_env(str(_TEMPLATES_DIR))
    html = env.get_template("staff_fab.html").render(active=active, links=links, menu_icon=_MENU_ICON)
    return RawHTML(html)
