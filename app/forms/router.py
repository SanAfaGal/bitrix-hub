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
from app.flows.registry_live_check import check_registration_number_live, confirm_registration_number_match
from app.forms.cleaning import slugify_filename
from app.forms.filler import build_blank_template, decode_signature_png, fill_and_sign
from app.forms.link_token import verify_deal_id_token
from app.forms.models import (
    BrokerageAuthorizationPayload,
    CleanSignaturePhotoPayload,
    ConfirmMatriculaMatchPayload,
    VerifyRegistrationNumberPayload,
)
from app.forms.page import (
    CLEAN_SIGNATURE_PATH,
    CONFIRM_MATRICULA_MATCH_PATH,
    FORM_PATH,
    TEMPLATE_PATH_URL,
    VERIFY_MATRICULA_PATH,
    render_already_signed_html,
    render_form_html,
    render_link_invalid_html,
)
from app.shared.rate_limit import rate_limit
from app.forms.settings import load_form_link_secret
from app.forms.signature_cleaner import clean_signature_photo
from app.waha.deps import get_waha_client
from app.xposure.deps import get_xposure_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Formularios"])

# La limpieza con OpenCV es lo más caro en CPU de este router — más permisivo
# que el envío final (que además genera el PDF), pero sigue acotado.
_CLEAN_SIGNATURE_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
_SUBMIT_FORM_RATE_LIMIT = {"max_requests": 6, "window_seconds": 60}
_VERIFY_MATRICULA_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
_CONFIRM_MATRICULA_MATCH_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}


def _limit_clean_signature(request: Request) -> None:
    rate_limit(request, "limpiar-firma", **_CLEAN_SIGNATURE_RATE_LIMIT)


def _limit_submit_form(request: Request) -> None:
    rate_limit(request, "enviar-formulario", **_SUBMIT_FORM_RATE_LIMIT)


def _limit_verify_matricula(request: Request) -> None:
    rate_limit(request, "verify-matricula", **_VERIFY_MATRICULA_RATE_LIMIT)


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
    """Solo los campos del inmueble que ya tienen mapeo definido a Bitrix.

    `location` queda pendiente: todavía no se define qué campo de Bitrix
    (sector/zona/ciudad) le corresponde, así que por ahora solo va al PDF.
    """
    return PropertyListing(
        property_type=payload.property_type,
        address=payload.address,
        expected_sale_price=payload.sale_price,
        registration_number=payload.registration_number or None,
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
        deal_id, filename, pdf_bytes, _property_listing_from_payload(payload), crm_client, get_waha_client
    )
