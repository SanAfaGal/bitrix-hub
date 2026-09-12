"""Página de inicio ("/"): accesos a Interno y Admin desde una sola URL."""
from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.auth.deps import is_admin_email, require_staff_user
from app.shared.html_templates import RawHTML, render_template
from app.shared.staff_nav import staff_fab_html

router = APIRouter(tags=["Inicio"])

_HOME_PATH = Path(__file__).parent / "templates" / "home.html"


def _header_html(staff_name: str) -> RawHTML:
    """Mismo header que `app/interno/router.py::_header_html`, con la insignia
    "Inicio" — duplicado a propósito en vez de compartido: son dos páginas que
    hoy cambian por separado y `app/interno/` es privado de ese paquete."""
    initial = escape(staff_name.strip()[:1].upper() or "?")
    safe_name = escape(staff_name)
    return RawHTML(
        '<header class="topbar">'
        '<div class="topbar__brand">'
        '<img class="topbar__logo" src="/static/imgs/logo_short.webp" alt="Alberto Álvarez">'
        '<div class="topbar__identity">'
        '<span class="topbar__name">Alberto Álvarez</span>'
        '<span class="topbar__badge">Inicio</span>'
        "</div>"
        "</div>"
        '<div class="topbar__session">'
        f'<span class="topbar__avatar">{initial}</span>'
        '<span class="topbar__user">'
        f'<span class="topbar__user-name">{safe_name}</span>'
        '<span class="topbar__user-status">Sesión iniciada</span>'
        "</span>"
        '<form method="post" action="/auth/logout">'
        '<button type="submit" class="topbar__logout" aria-label="Cerrar sesión" title="Cerrar sesión">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>'
        "</svg>"
        "</button>"
        "</form>"
        "</div>"
        "</header>"
    )


def _home_card_html(*, href: str, icon_svg: str, title: str, subtitle: str, enabled: bool, disabled_hint: str = "") -> RawHTML:
    if enabled:
        return RawHTML(
            f'<a class="home-card" href="{href}">'
            f'<span class="home-card__icon">{icon_svg}</span>'
            '<span class="home-card__body">'
            f'<span class="home-card__title">{escape(title)}</span>'
            f'<span class="home-card__subtitle">{escape(subtitle)}</span>'
            "</span>"
            "</a>"
        )
    return RawHTML(
        '<div class="home-card home-card--disabled" title="' + escape(disabled_hint) + '">'
        f'<span class="home-card__icon">{icon_svg}</span>'
        '<span class="home-card__body">'
        f'<span class="home-card__title">{escape(title)}</span>'
        f'<span class="home-card__subtitle">{escape(disabled_hint or subtitle)}</span>'
        "</span>"
        "</div>"
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
