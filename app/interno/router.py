"""Páginas privadas del staff: crear un lead y, opcionalmente, iniciar de inmediato
la Autorización de Corretaje reusando los datos ya capturados."""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.auth.deps import require_staff_user
from app.crm.deps import get_crm_client
from app.crm.protocol import SOURCE_CHANNELS
from app.flows.interno_nuevo_lead import process_nuevo_lead
from app.flows.settings import load_public_base_url
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.forms.link_token import sign_deal_id
from app.forms.models import PROPERTY_TYPES
from app.forms.page import FORM_PATH
from app.forms.settings import load_form_link_secret
from app.interno.models import NuevoLeadPayload
from app.interno.page_script import NUEVO_LEAD_SCRIPT
from app.shared import idempotency
from app.shared.field_specs import FIELD_SPECS
from app.shared.html_templates import RawHTML, render_template
from app.shared.phone_countries import DEFAULT_PHONE_COUNTRY_CODE, PHONE_COUNTRIES, phone_country_by_code
from app.waha.deps import get_waha_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interno", tags=["Interno"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_NUEVO_LEAD_PATH = _TEMPLATES_DIR / "nuevo_lead.html"
_LEAD_DETAIL_PATH = _TEMPLATES_DIR / "lead_detail.html"


def _header_html(staff_name: str) -> RawHTML:
    """Header propio de interno: marca + insignia "Interno" a la izquierda
    (para no confundirlo con el formulario público) y la sesión activa a la
    derecha (avatar con inicial, nombre y botón de cerrar sesión) — mismo
    header en `nuevo_lead.html` y `lead_detail.html`, armado acá una sola vez
    en vez de duplicar el marcado en las dos plantillas."""
    from html import escape

    initial = escape(staff_name.strip()[:1].upper() or "?")
    safe_name = escape(staff_name)
    return RawHTML(
        '<header class="topbar">'
        '<div class="topbar__brand">'
        '<img class="topbar__logo" src="/static/imgs/logo_short.webp" alt="Alberto Álvarez">'
        '<div class="topbar__identity">'
        '<span class="topbar__name">Alberto Álvarez</span>'
        '<span class="topbar__badge">Interno</span>'
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


def _flash_html(message: str | None, *, error: bool = False) -> RawHTML:
    if not message:
        return RawHTML("")
    css_class = "alert--error" if error else "alert--success"
    from html import escape

    return RawHTML(f'<div class="alert {css_class}">{escape(message)}</div>')


def _property_type_options_html(selected: str | None) -> RawHTML:
    from html import escape

    options = ['<option value="" disabled selected>Selecciona…</option>' if not selected else ""]
    for value in PROPERTY_TYPES:
        is_selected = " selected" if value == selected else ""
        options.append(f'<option value="{escape(value)}"{is_selected}>{escape(value)}</option>')
    return RawHTML("".join(options))


def _source_channel_options_html(selected: str | None) -> RawHTML:
    from html import escape

    options = ['<option value="" disabled selected>Selecciona…</option>' if not selected else ""]
    for identifier, label in SOURCE_CHANNELS:
        is_selected = " selected" if identifier == selected else ""
        options.append(f'<option value="{escape(identifier)}"{is_selected}>{escape(label)}</option>')
    return RawHTML("".join(options))


def _phone_country_options_html(selected_code: str) -> RawHTML:
    from html import escape

    items = []
    for country in PHONE_COUNTRIES:
        is_selected = " phone-country-list__item--active" if country["code"] == selected_code else ""
        items.append(
            f'<li class="phone-country-list__item{is_selected}" role="option" '
            f'data-code="{escape(country["code"])}" data-iso2="{escape(country["iso2"])}" tabindex="-1">'
            f'<img class="phone-country-list__flag" src="https://flagcdn.com/w20/{escape(country["iso2"])}.png" alt="">'
            f'<span class="phone-country-list__name">{escape(country["name"])}</span>'
            f'<span class="phone-country-list__code">+{escape(country["code"])}</span>'
            "</li>"
        )
    return RawHTML("".join(items))


def _phone_badge_html(selected_code: str) -> RawHTML:
    from html import escape

    country = phone_country_by_code(selected_code)
    return RawHTML(
        f'<img class="phone-group__flag" id="phone-country-flag" src="https://flagcdn.com/w40/{escape(country["iso2"])}.png" alt="">'
        f'<span id="phone-country-label">+{escape(country["code"])}</span>'
    )


def _coverage_warning_html(message: str | None) -> RawHTML:
    if not message:
        return RawHTML("")
    from html import escape

    return RawHTML(
        '<div class="coverage-warning">'
        '<div class="coverage-warning__header">'
        '<span class="coverage-warning__icon">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
        "</svg>"
        "</span>"
        '<span class="coverage-warning__title">Fuera de la zona de cobertura</span>'
        "</div>"
        f'<p class="coverage-warning__message">{escape(message)}</p>'
        '<label class="coverage-warning__checkbox">'
        '<input type="checkbox" name="coverage_override" value="true">'
        "<span>Continuar de todas formas</span>"
        "</label>"
        "</div>"
    )


def _field_text_kwargs() -> dict[str, str]:
    """Label y placeholder de cada campo, leídos de `FIELD_SPECS` — mismo
    texto que el formulario público para los campos que comparten (ver
    app/shared/field_specs.py), en vez de una copia a mano en la plantilla.
    El hint NO viaja acá a propósito: cambia según el formulario (interno
    captura en un momento distinto, con contexto distinto), así que cada
    plantilla escribe el suyo directamente."""
    kwargs: dict[str, str] = {}
    for name, spec in FIELD_SPECS.items():
        kwargs[f"label_{name}"] = spec.label
        kwargs[f"placeholder_{name}"] = spec.placeholder or ""
    return kwargs


def _render_nuevo_lead(
    *,
    staff_name: str,
    flash: str | None = None,
    flash_error: bool = False,
    coverage_message: str | None = None,
    interested_party: str = "",
    owner_phone: str = "",
    phone_country_code: str = DEFAULT_PHONE_COUNTRY_CODE,
    email: str = "",
    property_type: str | None = None,
    address: str = "",
    location: str = "",
    location_sector_code: str = "",
    sale_price: str = "",
    source_channel: str | None = None,
) -> str:
    return render_template(
        _NUEVO_LEAD_PATH,
        staff_name=staff_name,
        header_html=_header_html(staff_name),
        flash_html=_flash_html(flash, error=flash_error),
        idempotency_token=idempotency.new_token(),
        interested_party=interested_party,
        owner_phone=owner_phone,
        phone_country_code=phone_country_code,
        phone_badge_html=_phone_badge_html(phone_country_code),
        phone_country_options_html=_phone_country_options_html(phone_country_code),
        email=email,
        property_type_options_html=_property_type_options_html(property_type),
        address=address,
        location=location,
        location_sector_code=location_sector_code,
        sale_price=sale_price,
        source_channel_options_html=_source_channel_options_html(source_channel),
        coverage_warning_html=_coverage_warning_html(coverage_message),
        script_html=RawHTML(NUEVO_LEAD_SCRIPT),
        **_field_text_kwargs(),
    )


@router.get("/nuevo-lead", response_class=HTMLResponse, summary="Formulario interno para crear un lead")
def get_nuevo_lead(staff_user: dict[str, str] = Depends(require_staff_user)) -> HTMLResponse:
    return HTMLResponse(_render_nuevo_lead(staff_name=staff_user["name"]))


@router.post("/nuevo-lead", summary="Crea el contacto y la negociación en Bitrix", response_model=None)
def post_nuevo_lead(
    staff_user: dict[str, str] = Depends(require_staff_user),
    interested_party: str = Form(...),
    owner_phone: str = Form(...),
    phone_country_code: str = Form(default=DEFAULT_PHONE_COUNTRY_CODE),
    email: str = Form(default=""),
    property_type: str = Form(...),
    address: str = Form(...),
    location: str = Form(...),
    location_sector_code: str = Form(...),
    sale_price: str = Form(default=""),
    source_channel: str = Form(...),
    coverage_override: str = Form(default=""),
    idempotency_token: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    form_values = dict(
        interested_party=interested_party,
        owner_phone=owner_phone,
        phone_country_code=phone_country_code,
        email=email,
        property_type=property_type,
        address=address,
        location=location,
        location_sector_code=location_sector_code,
        sale_price=sale_price,
        source_channel=source_channel,
    )

    try:
        payload = NuevoLeadPayload(
            interested_party=interested_party,
            owner_phone=owner_phone,
            phone_country_code=phone_country_code,
            email=email or None,
            property_type=property_type,
            address=address,
            location=location,
            location_sector_code=location_sector_code,
            sale_price=sale_price,
            source_channel=source_channel,
            coverage_override=coverage_override == "true",
            idempotency_token=idempotency_token,
        )
    except ValidationError as exc:
        message = exc.errors()[0]["msg"] if exc.errors() else "Datos inválidos."
        return HTMLResponse(_render_nuevo_lead(staff_name=staff_user["name"], flash=message, flash_error=True, **form_values))

    try:
        crm_client = get_crm_client()
    except (HTTPException, RuntimeError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return HTMLResponse(
            _render_nuevo_lead(staff_name=staff_user["name"], flash=str(detail), flash_error=True, **form_values)
        )

    result = process_nuevo_lead(payload, crm_client, staff_user["email"])

    if result.blocked:
        return HTMLResponse(
            _render_nuevo_lead(
                staff_name=staff_user["name"],
                coverage_message=result.message,
                **form_values,
            )
        )

    if not result.ok:
        return HTMLResponse(
            _render_nuevo_lead(staff_name=staff_user["name"], flash=result.message, flash_error=True, **form_values)
        )

    if not idempotency.consume(payload.idempotency_token):
        # Reenvío del mismo formulario (doble clic) después de ya haber creado el
        # lead en esta misma corrida — find_or_create ya es idempotente por
        # teléfono, así que no hay riesgo de duplicar, pero evitamos la escritura
        # repetida en Bitrix.
        logger.info("Token de idempotencia ya usado para el lead recién creado %s, no se repite la escritura", result.deal_id)

    redirect_url = f"/interno/lead/{result.deal_id}"
    if result.reused_existing_deal:
        # Este contacto ya tenía un deal de consignación abierto — no se creó uno
        # nuevo, se reusó el existente, y update_property_listing acaba de pisar
        # los datos de inmueble que ya tuviera cargados.
        flash_message = "Este contacto ya tenía un lead de consignación — se actualizó el inmueble sobre ese lead existente."
        redirect_url += f"?flash={quote(flash_message)}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/lead/{deal_id}", response_class=HTMLResponse, summary="Resumen de un lead y siguientes pasos")
def get_lead_detail(
    deal_id: str, flash: str | None = None, staff_user: dict[str, str] = Depends(require_staff_user)
) -> HTMLResponse:
    try:
        crm_client = get_crm_client()
    except (HTTPException, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc) if isinstance(exc, RuntimeError) else exc.detail) from exc

    if not crm_client.deal_exists(deal_id):
        raise HTTPException(status_code=404, detail="Lead no encontrado.")

    deal = crm_client.get_deal(deal_id)
    contact_id = crm_client.get_deal_contact_id(deal)
    owner_full_name = ""
    if contact_id:
        contact = crm_client.get_contact(contact_id)
        owner_full_name = crm_client.get_contact_full_name(contact) or ""

    listing = crm_client.get_property_listing(deal_id)

    try:
        link_secret = load_form_link_secret()
        token = sign_deal_id(deal_id, link_secret)
        public_form_url = f"{FORM_PATH}?deal_id={deal_id}&token={token}"
    except RuntimeError:
        public_form_url = FORM_PATH

    return HTMLResponse(
        render_template(
            _LEAD_DETAIL_PATH,
            staff_name=staff_user["name"],
            header_html=_header_html(staff_user["name"]),
            deal_id=deal_id,
            flash_html=_flash_html(flash),
            owner_full_name=owner_full_name or "(sin nombre)",
            property_type=listing.property_type or "(pendiente)",
            address=listing.address or "(pendiente)",
            # `PropertyListing` ya no trae un texto de ubicación legible: el
            # deal solo guarda el vínculo al ítem del Smart Process de
            # Sectores (ver app.bitrix.fields.FIELD_DEAL_UBICACION_SECTOR),
            # no una copia de texto. Mostrar ese vínculo acá queda pendiente.
            location="(pendiente)",
            public_form_url=public_form_url,
        )
    )


@router.post(
    "/lead/{deal_id}/enviar-whatsapp",
    summary="Envía el enlace de Autorización de Corretaje por WhatsApp",
)
def post_enviar_whatsapp(
    deal_id: str, staff_user: dict[str, str] = Depends(require_staff_user)
) -> RedirectResponse:
    try:
        crm_client = get_crm_client()
        waha_client = get_waha_client()
        public_base_url = load_public_base_url()
        link_secret = load_form_link_secret()
    except (HTTPException, RuntimeError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return RedirectResponse(url=f"/interno/lead/{deal_id}?flash={quote(str(detail))}", status_code=303)

    result = process_welcome_and_authorization(deal_id, crm_client, waha_client, public_base_url, link_secret)
    flash = "Enlace enviado por WhatsApp." if result.get("ok") else result.get("error", "No se pudo enviar el enlace.")
    return RedirectResponse(url=f"/interno/lead/{deal_id}?flash={quote(str(flash))}", status_code=303)
