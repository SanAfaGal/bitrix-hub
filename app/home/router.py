"""Página de inicio ("/"): accesos a Interno y Admin desde una sola URL."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.auth.deps import is_admin_email, require_staff_user
from app.shared.html_templates import RawHTML, render_template
from app.shared.jinja_env import get_env
from app.shared.staff_nav import staff_fab_html

router = APIRouter(tags=["Inicio"])

_HOME_PATH = Path(__file__).parent / "templates" / "home.html"
_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"


def _fragments():
    return get_env(str(_TEMPLATES_DIR)).get_template("_fragments.html").module


def _header_html(staff_name: str) -> RawHTML:
    """Mismo header que `app/interno/router.py::_header_html`, con la insignia
    "Inicio" — duplicado a propósito en vez de compartido: son dos páginas que
    hoy cambian por separado y `app/interno/` es privado de ese paquete."""
    initial = staff_name.strip()[:1].upper() or "?"
    return RawHTML(_fragments().header(staff_name, initial))


def _home_card_html(*, href: str, icon_svg: str, title: str, subtitle: str, enabled: bool, disabled_hint: str = "") -> RawHTML:
    return RawHTML(
        _fragments().home_card(href, icon_svg, title, subtitle, enabled, disabled_hint)
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


@router.get("/", response_class=HTMLResponse, summary="Inicio: accesos a Interno y Admin")
def get_home(user: dict = Depends(require_staff_user)) -> HTMLResponse:
    is_admin = is_admin_email(user["email"])
    lead_card = _home_card_html(
        href="/interno/nuevo-lead",
        icon_svg=_LEAD_ICON,
        title="Crear lead",
        subtitle="Registra un propietario y su inmueble en Bitrix.",
        enabled=True,
    )
    admin_card = _home_card_html(
        href="/admin",
        icon_svg=_ADMIN_ICON,
        title="Panel administrativo",
        subtitle="Plantillas de WhatsApp, comportamiento del bot, prospectos y cobertura.",
        enabled=is_admin,
        disabled_hint="Tu cuenta no tiene acceso al panel admin.",
    )
    return HTMLResponse(
        render_template(
            _HOME_PATH,
            header_html=_header_html(user["name"]),
            lead_card_html=lead_card,
            admin_card_html=admin_card,
            staff_fab_html=staff_fab_html(active="home", is_admin=is_admin),
        )
    )
