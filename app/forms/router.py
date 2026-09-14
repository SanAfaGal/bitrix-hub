"""Endpoint público: formulario de Autorización de Corretaje con firma desde el celular."""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.crm.deps import get_crm_client
from app.crm.protocol import PropertyListing
from app.flows.brokerage_authorization_signed import process_authorization_signed
from app.flows.whatsapp_bot import conversation_store
from app.flows.registry_live_check import check_registration_number_live, confirm_registration_number_match
from app.forms.coverage import is_location_covered
from app.forms.cleaning import slugify_filename
from app.forms.filler import build_blank_template, decode_signature_png, fill_and_sign
from app.forms.link_token import verify_deal_id_token
from app.forms.models import (
    BrokerageAuthorizationPayload,
    CleanSignaturePhotoPayload,
    ConfirmMatriculaMatchPayload,
    VerifyLocationCoveragePayload,
    VerifyRegistrationNumberPayload,
)
from app.forms.page import (
    CLEAN_SIGNATURE_PATH,
    CONFIRM_MATRICULA_MATCH_PATH,
    ESTADO_SERVICIOS_PATH,
    FORM_PATH,
    TEMPLATE_PATH_URL,
    VERIFY_COBERTURA_PATH,
    VERIFY_MATRICULA_PATH,
    render_already_signed_html,
    render_form_html,
    render_link_invalid_html,
)
from app.location_catalog import client as location_catalog_client
from app.shared.rate_limit import rate_limit
from app.forms.settings import load_form_link_secret
from app.forms.signature_cleaner import clean_signature_photo
from app.waha.deps import get_waha_client
from app.xposure.client import XposureClient
from app.xposure.deps import get_xposure_client
from app.xposure.settings import load_xposure_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Formularios"])

# La limpieza con OpenCV es lo más caro en CPU de este router — más permisivo
# que el envío final (que además genera el PDF), pero sigue acotado.
_CLEAN_SIGNATURE_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
_SUBMIT_FORM_RATE_LIMIT = {"max_requests": 6, "window_seconds": 60}
_VERIFY_MATRICULA_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
_CONFIRM_MATRICULA_MATCH_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
_VERIFY_COBERTURA_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
# Más permisivo que los demás: es solo lectura de estado, sin efecto en nada,
# se puede llamar varias veces por sesión (cada vez que se muestra un paso).
_ESTADO_SERVICIOS_RATE_LIMIT = {"max_requests": 30, "window_seconds": 60}


def _limit_clean_signature(request: Request) -> None:
    rate_limit(request, "limpiar-firma", **_CLEAN_SIGNATURE_RATE_LIMIT)


def _limit_submit_form(request: Request) -> None:
    rate_limit(request, "enviar-formulario", **_SUBMIT_FORM_RATE_LIMIT)


def _limit_verify_matricula(request: Request) -> None:
    rate_limit(request, "verify-matricula", **_VERIFY_MATRICULA_RATE_LIMIT)


def _limit_verify_cobertura(request: Request) -> None:
    rate_limit(request, "verify-cobertura", **_VERIFY_COBERTURA_RATE_LIMIT)


def _limit_estado_servicios(request: Request) -> None:
    rate_limit(request, "estado-servicios", **_ESTADO_SERVICIOS_RATE_LIMIT)


def _limit_confirm_matricula_match(request: Request) -> None:
    rate_limit(request, "confirm-matricula-match", **_CONFIRM_MATRICULA_MATCH_RATE_LIMIT)


_YES_NO_LABELS = {"si": "Sí", "no": "No"}

# Campos de plata: la plantilla ya trae el "$" impreso antes del blanco (ver
# app/forms/filler.py), así que el valor va sin signo — con separador de
# miles (formato colombiano, punto) y la moneda explícita al final.
_MONEY_FIELDS = {"sale_price", "outstanding_debt"}


def _format_field_value(key: str, value: object) -> str:
    if value is None:
        return ""
    if key in _MONEY_FIELDS:
        return f"{value:,}".replace(",", ".") + " COP"
    return str(value)


def _pdf_field_values(payload: BrokerageAuthorizationPayload) -> dict[str, str]:
    """`model_dump()` trae ints/None (sale_price, outstanding_debt, term_months) y
    "si"/"no" (mortgage_loan, leasing) — el AcroForm solo acepta texto."""
    values = payload.model_dump(exclude={"signature_png"})
    values["mortgage_loan"] = _YES_NO_LABELS[values["mortgage_loan"]]
    values["leasing"] = _YES_NO_LABELS[values["leasing"]]
    return {key: _format_field_value(key, value) for key, value in values.items()}


def _decode_image_data_url_or_400(data_url: str) -> bytes:
    try:
        return decode_signature_png(data_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _content_disposition(filename: str, *, inline: bool = False) -> str:
    """Nombre de archivo "normal" (con espacios/acentos) para lo que el usuario descarga.

    La URL sigue en minúsculas y con guiones (convención web); el nombre del
    archivo descargado es aparte y va legible tal como lo vería el usuario
    en su explorador de archivos. `filename*` (RFC 5987) lleva los acentos;
    `filename` es el fallback ASCII para navegadores viejos.

    `inline=True` deja que el navegador lo muestre en la pestaña (p. ej. la
    plantilla sin diligenciar, que el cliente solo quiere leer antes de
    llenar el formulario) en vez de forzar la descarga.
    """
    disposition = "inline" if inline else "attachment"
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


def _is_valid_link(deal_id: str, token: str | None) -> bool:
    """El link solo es válido para el `deal_id` que lo firmó (ver app/forms/link_token.py)."""
    try:
        secret = load_form_link_secret()
    except RuntimeError:
        logger.exception("Falta configuración para validar el link del formulario")
        return False
    return verify_deal_id_token(deal_id, token, secret)


def _is_already_signed(deal_id: str) -> bool:
    try:
        crm_client = get_crm_client()
    except (HTTPException, RuntimeError):
        return False
    deal = crm_client.get_deal(deal_id)
    return crm_client.get_authorization_status(deal) == "firmada"


def _prefill_from_deal(deal_id: str) -> dict[str, str]:
    """Solo los campos ya capturados por un lead creado desde app/interno/ (o
    cualquier otro origen que haya llamado `update_property_listing`) — el
    propietario no debería repetir información que el captador ya guardó en
    Bitrix. Ver el docstring de `render_form_html` para qué campos cubre.

    `location`/`location_sector_code` van acá (no solo a `_location_prefill_from_deal`)
    para que también aparezcan ya escritos si el cliente usa "Corregir" sobre
    ese paso — `render_form_html` los usa además para saltarse el paso del
    wizard, ver `get_brokerage_authorization_form`."""
    try:
        crm_client = get_crm_client()
    except (HTTPException, RuntimeError):
        return {}
    listing = crm_client.get_property_listing(deal_id)
    prefill: dict[str, str] = {}
    if listing.property_type:
        prefill["property_type"] = listing.property_type
    if listing.address:
        prefill["address"] = listing.address
    if listing.expected_sale_price:
        prefill["sale_price"] = str(listing.expected_sale_price)
    if listing.location_label:
        prefill["location"] = listing.location_label
    if listing.location_sector_code:
        prefill["location_sector_code"] = listing.location_sector_code

    deal = crm_client.get_deal(deal_id)
    contact_id = crm_client.get_deal_contact_id(deal) if deal else None
    if contact_id:
        contact = crm_client.get_contact(contact_id)
        full_name = crm_client.get_contact_full_name(contact) if contact else None
        email = crm_client.get_contact_email(contact) if contact else None
        if full_name:
            prefill["interested_party"] = full_name
        if email:
            prefill["email"] = email

    return prefill


def _location_prefill_from_deal(prefill: dict[str, str]) -> dict[str, str] | None:
    """El wizard solo puede saltarse el paso de ubicación (ver
    `get_brokerage_authorization_form`) si tiene los dos datos que necesita
    para darla por confirmada — el sector ya se validó por cobertura cuando
    el captador creó el lead (`app.flows.interno_nuevo_lead.process_nuevo_lead`),
    así que no hace falta repetir ese chequeo acá."""
    location = prefill.get("location")
    sector_code = prefill.get("location_sector_code")
    if location and sector_code:
        return {"location": location, "sector_code": sector_code}
    return None


@router.get(
    FORM_PATH,
    response_class=HTMLResponse,
    summary="Formulario de Autorización de Corretaje (llenar y firmar desde el celular)",
)
def get_brokerage_authorization_form(deal_id: str | None = None, token: str | None = None) -> HTMLResponse:
    if deal_id:
        if not _is_valid_link(deal_id, token):
            return HTMLResponse(render_link_invalid_html())
        if _is_already_signed(deal_id):
            return HTMLResponse(render_already_signed_html())
        prefill = _prefill_from_deal(deal_id)
        location_prefill = _location_prefill_from_deal(prefill)
        return HTMLResponse(
            render_form_html(deal_id=deal_id, token=token, prefill=prefill, location_prefill=location_prefill)
        )
    return HTMLResponse(render_form_html(deal_id=deal_id, token=token))


@router.post(
    CLEAN_SIGNATURE_PATH,
    summary="Limpia el fondo de una foto de firma subida (OpenCV: Otsu + morfología)",
)
def post_clean_signature_photo(
    payload: CleanSignaturePhotoPayload, _: None = Depends(_limit_clean_signature)
) -> dict[str, str]:
    raw_image_bytes = _decode_image_data_url_or_400(payload.image_png)

    try:
        cleaned_png_bytes = clean_signature_photo(raw_image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"cleaned_png": "data:image/png;base64," + base64.b64encode(cleaned_png_bytes).decode()}


@router.post(
    VERIFY_MATRICULA_PATH,
    summary="Chequeo en vivo (paso del wizard): matrícula ya publicada en el MLS vía Xposure",
)
def post_verify_registration_number(
    payload: VerifyRegistrationNumberPayload, _: None = Depends(_limit_verify_matricula)
) -> dict[str, Any]:
    """Paso del wizard después de la ubicación: el cliente teclea la matrícula/ID y esto la
    consulta en Xposure en vivo, antes de mostrarle el resto del formulario. Independiente de
    la cobertura por zona (app/forms/coverage.py, sin usar en este flujo). Si hay `deal_id`,
    deja constancia en Bitrix (`check_registration_number_live`) aunque el cliente quede
    bloqueado acá."""
    crm_client = None
    if payload.deal_id:
        if not _is_valid_link(payload.deal_id, payload.token):
            raise HTTPException(status_code=403, detail="Enlace inválido.")
        try:
            crm_client = get_crm_client()
        except (HTTPException, RuntimeError):
            logger.exception("No se pudo obtener el cliente de CRM para verificar-matricula")
            crm_client = None

    return check_registration_number_live(
        payload.registration_number, get_xposure_client, crm_client=crm_client, deal_id=payload.deal_id
    )


@router.post(
    CONFIRM_MATRICULA_MATCH_PATH,
    summary="Paso del wizard: el cliente confirma si el inmueble encontrado en Xposure es el suyo",
)
def post_confirm_matricula_match(
    payload: ConfirmMatriculaMatchPayload, _: None = Depends(_limit_confirm_matricula_match)
) -> dict[str, Any]:
    """Después de que `post_verify_registration_number` encuentra un duplicado, el wizard le
    pregunta al cliente "¿es este tu inmueble?" antes de bloquear — este endpoint recibe esa
    respuesta y recién ahí deja constancia en Bitrix (`confirm_registration_number_match`), para
    no marcar Duplicado en un deal sobre un match que la persona no confirmó."""
    crm_client = None
    if payload.deal_id:
        if not _is_valid_link(payload.deal_id, payload.token):
            raise HTTPException(status_code=403, detail="Enlace inválido.")
        try:
            crm_client = get_crm_client()
        except (HTTPException, RuntimeError):
            logger.exception("No se pudo obtener el cliente de CRM para confirmar-matricula-match")
            crm_client = None

    return confirm_registration_number_match(
        payload.registration_number,
        payload.url,
        payload.confirmed,
        crm_client=crm_client,
        deal_id=payload.deal_id,
    )


@router.post(
    VERIFY_COBERTURA_PATH,
    summary="Chequeo en vivo (paso del wizard): cobertura de ventas por ubicación",
)
def post_verify_location_coverage(
    payload: VerifyLocationCoveragePayload, _: None = Depends(_limit_verify_cobertura)
) -> dict[str, Any]:
    """Paso del wizard justo después de que el cliente elige una ubicación de la lista de
    sugerencias: consulta cobertura_ventas para ese sector_code en vivo (nunca cacheada, ver
    app/location_catalog/client.py::get_sector_coverage) antes de dejarlo avanzar a matrícula.
    Sin efecto en Bitrix/CRM a propósito (a diferencia de verify-matricula): bloquear por
    falta de cobertura es una decisión del lado del cliente, no se deja constancia en el deal."""
    if is_location_covered(payload.sector_code):
        return {"covered": True}
    return {
        "covered": False,
        "message": "Por ahora no tenemos cobertura de ventas en esta zona. Contacta a tu asesor si crees que esto es un error.",
    }


def _is_xposure_reachable() -> bool:
    try:
        base_url, username, password = load_xposure_settings()
    except RuntimeError:
        return False
    return XposureClient(base_url, username, password).is_reachable()


@router.get(
    ESTADO_SERVICIOS_PATH,
    summary="Estado en vivo de los servicios externos que usa el wizard (indicador visual)",
)
def get_estado_servicios(_: None = Depends(_limit_estado_servicios)) -> dict[str, bool]:
    """Solo informativo: alimenta el puntico de estado del wizard, no bloquea nada por sí
    mismo — la decisión real de bloquear o dejar pasar la toma is_location_covered/
    check_registration_number_live, que ya fallan abiertos cuando no pueden determinar algo."""
    return {"mobilia_dwh": location_catalog_client.is_reachable(), "xposure": _is_xposure_reachable()}


@router.get(
    TEMPLATE_PATH_URL,
    summary="Muestra la plantilla sin diligenciar (para que el cliente la lea antes de llenar el formulario)",
)
def get_brokerage_authorization_template() -> Response:
    return Response(
        content=build_blank_template(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": _content_disposition(
                "Autorización de Corretaje - Plantilla.pdf", inline=True
            )
        },
    )


@router.post(
    FORM_PATH,
    summary="Genera el PDF de Autorización de Corretaje diligenciado y firmado",
)
def post_brokerage_authorization_form(
    payload: BrokerageAuthorizationPayload, _: None = Depends(_limit_submit_form)
) -> Response:
    if not payload.signature_png:
        raise HTTPException(status_code=400, detail="Falta la firma.")

    if payload.deal_id:
        if not _is_valid_link(payload.deal_id, payload.token):
            raise HTTPException(status_code=403, detail="Enlace inválido.")
        if _is_already_signed(payload.deal_id):
            raise HTTPException(status_code=409, detail="Esta autorización ya fue firmada.")

    signature_png_bytes = _decode_image_data_url_or_400(payload.signature_png)

    values = _pdf_field_values(payload)

    try:
        pdf_bytes = fill_and_sign(values, signature_png_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Error generando el PDF de Autorización de Corretaje")
        raise HTTPException(status_code=500, detail="No se pudo generar el documento.") from None

    signed_at = datetime.now()

    if payload.deal_id:
        _mark_as_signed(payload, pdf_bytes, signed_at)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(_client_download_filename(signed_at))},
    )


def _client_download_filename(signed_at: datetime) -> str:
    return f"Autorización de Corretaje - Firmada {signed_at.strftime('%d-%m-%Y %H-%M')}.pdf"


def _signed_pdf_filename(deal_id: str, address: str, signed_at: datetime) -> str:
    fecha = signed_at.strftime("%Y%m%d_%H%M%S")
    return f"Autorizacion_{deal_id}_{slugify_filename(address)}_{fecha}.pdf"


def _property_listing_from_payload(payload: BrokerageAuthorizationPayload) -> PropertyListing:
    """Campos del inmueble con mapeo a Bitrix.

    `location` (el texto libre con sugerencias del `<datalist>`) no se manda
    — solo se usa para armar el PDF. `location_sector_code` sí se manda: el
    CRM lo resuelve internamente contra el Smart Process de Sectores para
    vincular el campo "[Ventas] Ubicación" del deal (ver
    `PropertyListing.location_sector_code`).
    """
    return PropertyListing(
        property_type=payload.property_type,
        address=payload.address,
        expected_sale_price=payload.sale_price,
        registration_number=payload.registration_number or None,
        location_sector_code=payload.location_sector_code,
    )


def _mark_as_signed(payload: BrokerageAuthorizationPayload, pdf_bytes: bytes, signed_at: datetime) -> None:
    """Delega a `app.flows.brokerage_authorization_signed` (combina CRM + Waha, ver su
    docstring) — este router solo arma los datos propios del formulario."""
    deal_id = payload.deal_id
    try:
        crm_client = get_crm_client()
    except (HTTPException, RuntimeError):
        logger.exception("No se pudo obtener el cliente de CRM para marcar la firma del deal %s", deal_id)
        return

    filename = _signed_pdf_filename(deal_id, payload.address, signed_at)
    process_authorization_signed(
        deal_id,
        filename,
        pdf_bytes,
        _property_listing_from_payload(payload),
        crm_client,
        get_waha_client,
        conversation_store,
    )
