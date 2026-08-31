"""Endpoint público: formulario de Autorización de Corretaje con firma desde el celular."""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.crm.deps import get_crm_client
from app.forms.cleaning import slugify_filename
from app.forms.filler import build_blank_template, decode_signature_png, fill_and_sign
from app.forms.link_token import verify_deal_id_token
from app.forms.models import BrokerageAuthorizationPayload, CleanSignaturePhotoPayload
from app.forms.page import (
    CLEAN_SIGNATURE_PATH,
    FORM_PATH,
    TEMPLATE_PATH_URL,
    render_already_signed_html,
    render_form_html,
    render_link_invalid_html,
)
from app.forms.rate_limit import rate_limit
from app.forms.settings import load_form_link_secret, load_signed_form_drive_folder_id
from app.forms.signature_cleaner import clean_signature_photo
from app.message_templates import store as templates_store
from app.waha.client import WahaClient
from app.waha.deps import get_waha_client
from app.waha.phone import to_chat_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Formularios"])

# La limpieza con OpenCV es lo más caro en CPU de este router — más permisivo
# que el envío final (que además genera el PDF), pero sigue acotado.
_CLEAN_SIGNATURE_RATE_LIMIT = {"max_requests": 15, "window_seconds": 60}
_SUBMIT_FORM_RATE_LIMIT = {"max_requests": 6, "window_seconds": 60}


def _limit_clean_signature(request: Request) -> None:
    rate_limit(request, "limpiar-firma", **_CLEAN_SIGNATURE_RATE_LIMIT)


def _limit_submit_form(request: Request) -> None:
    rate_limit(request, "enviar-formulario", **_SUBMIT_FORM_RATE_LIMIT)


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
    except Exception:
        logger.exception("Error generando el PDF de Autorización de Corretaje")
        raise HTTPException(status_code=500, detail="No se pudo generar el documento.") from None

    signed_at = datetime.now()

    if payload.deal_id:
        _mark_as_signed(payload.deal_id, payload.address, pdf_bytes, signed_at)

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


def _upload_signed_pdf(crm_client, deal_id: str, address: str, pdf_bytes: bytes, signed_at: datetime) -> str | None:
    try:
        folder_id = load_signed_form_drive_folder_id()
    except RuntimeError:
        logger.exception("Falta configuración para subir el PDF firmado al drive")
        return None
    filename = _signed_pdf_filename(deal_id, address, signed_at)
    return crm_client.upload_file(folder_id, filename, pdf_bytes)


def _mark_as_signed(deal_id: str, address: str, pdf_bytes: bytes, signed_at: datetime) -> None:
    """Deja constancia de la firma en el deal: sube el PDF al drive, comenta en el timeline
    (con el link al documento si la subida funcionó), marca el estado 'Firmada' y le avisa
    al cliente por WhatsApp que la recibimos.

    Best-effort: nunca rompe la descarga del PDF si Bitrix o Waha fallan.
    """
    try:
        crm_client = get_crm_client()
        file_url = _upload_signed_pdf(crm_client, deal_id, address, pdf_bytes, signed_at)
        comment = "El cliente firmó la Autorización de Corretaje."
        if file_url:
            comment += f" Documento firmado: {file_url}"
        crm_client.add_comment(deal_id, comment)
        crm_client.set_authorization_status(deal_id, "firmada")
        _notify_client_signed(crm_client, deal_id)
    except Exception:
        logger.exception("Error marcando la firma de la Autorización de Corretaje en el deal %s", deal_id)


def _notify_client_signed(crm_client, deal_id: str) -> None:
    """Le avisa al cliente por WhatsApp que su Autorización de Corretaje firmada llegó.

    Best-effort, silencioso si algo falta (sin contacto, sin teléfono, o
    falla Waha) — no debe romper `_mark_as_signed`, que ya deja la
    constancia importante (comentario + estado) en el deal aunque este
    aviso no se pueda mandar.
    """
    deal = crm_client.get_deal(deal_id)
    contact_id = crm_client.get_deal_contact_id(deal)
    if not contact_id:
        logger.warning("Deal %s firmado sin contacto vinculado, no se avisa por WhatsApp", deal_id)
        return

    contact = crm_client.get_contact(contact_id)
    raw_phone = crm_client.get_contact_phone(contact)
    chat_id = to_chat_id(raw_phone) if raw_phone else None
    if not chat_id:
        logger.warning("Deal %s firmado sin teléfono válido, no se avisa por WhatsApp", deal_id)
        return

    waha_client: WahaClient = get_waha_client()
    waha_client.send_text(chat_id, templates_store.get_template("whatsapp_authorization_signed_message"))
