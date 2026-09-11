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
from app.flows.interno_nuevo_lead import process_nuevo_lead
from app.flows.settings import load_public_base_url
from app.flows.welcome_authorization import process_welcome_and_authorization
from app.forms.link_token import sign_deal_id
from app.forms.models import PROPERTY_TYPES
from app.forms.page import FORM_PATH
from app.forms.settings import load_form_link_secret
from app.interno.models import NuevoLeadPayload
from app.shared import idempotency
from app.shared.html_templates import RawHTML, render_template
from app.waha.deps import get_waha_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interno", tags=["Interno"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_NUEVO_LEAD_PATH = _TEMPLATES_DIR / "nuevo_lead.html"
_LEAD_DETAIL_PATH = _TEMPLATES_DIR / "lead_detail.html"


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


def _coverage_warning_html(message: str | None) -> RawHTML:
    if not message:
        return RawHTML("")
    from html import escape

    return RawHTML(
        f'<div class="alert alert--warning"><p>{escape(message)}</p>'
        '<label class="field__checkbox"><input type="checkbox" name="coverage_override" value="true"> '
        "Continuar de todas formas (queda registrado en el deal)</label></div>"
    )


def _render_nuevo_lead(
    *,
    staff_name: str,
    flash: str | None = None,
    flash_error: bool = False,
    coverage_message: str | None = None,
    owner_full_name: str = "",
    owner_phone: str = "",
    owner_email: str = "",
    property_type: str | None = None,
    address: str = "",
    location: str = "",
    location_sector_code: str = "",
    expected_sale_price: str = "",
) -> str:
    return render_template(
        _NUEVO_LEAD_PATH,
        staff_name=staff_name,
        flash_html=_flash_html(flash, error=flash_error),
        idempotency_token=idempotency.new_token(),
        owner_full_name=owner_full_name,
        owner_phone=owner_phone,
        owner_email=owner_email,
        property_type_options_html=_property_type_options_html(property_type),
        address=address,
        location=location,
        location_sector_code=location_sector_code,
        expected_sale_price=expected_sale_price,
        coverage_warning_html=_coverage_warning_html(coverage_message),
    )


@router.get("/nuevo-lead", response_class=HTMLResponse, summary="Formulario interno para crear un lead")
def get_nuevo_lead(staff_user: dict[str, str] = Depends(require_staff_user)) -> HTMLResponse:
    return HTMLResponse(_render_nuevo_lead(staff_name=staff_user["name"]))


@router.post("/nuevo-lead", summary="Crea el contacto y la negociación en Bitrix", response_model=None)
def post_nuevo_lead(
    staff_user: dict[str, str] = Depends(require_staff_user),
    owner_full_name: str = Form(...),
    owner_phone: str = Form(...),
    owner_email: str = Form(default=""),
    property_type: str = Form(...),
    address: str = Form(...),
    location: str = Form(...),
    location_sector_code: str = Form(...),
    expected_sale_price: str = Form(default=""),
    coverage_override: str = Form(default=""),
    idempotency_token: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    form_values = dict(
        owner_full_name=owner_full_name,
        owner_phone=owner_phone,
        owner_email=owner_email,
        property_type=property_type,
        address=address,
        location=location,
        location_sector_code=location_sector_code,
        expected_sale_price=expected_sale_price,
    )

    try:
        payload = NuevoLeadPayload(
            owner_full_name=owner_full_name,
            owner_phone=owner_phone,
            owner_email=owner_email or None,
            property_type=property_type,
            address=address,
            location=location,
            location_sector_code=location_sector_code,
            expected_sale_price=expected_sale_price,
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

    return RedirectResponse(url=f"/interno/lead/{result.deal_id}", status_code=303)


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
            deal_id=deal_id,
            flash_html=_flash_html(flash),
            owner_full_name=owner_full_name or "(sin nombre)",
            property_type=listing.property_type or "(pendiente)",
            address=listing.address or "(pendiente)",
            location=listing.sector_zone_city or "(pendiente)",
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
