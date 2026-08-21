"""Endpoint público: formulario de Autorización de Corretaje con firma desde el celular."""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.bitrix.deps import get_bitrix_client
from app.forms.filler import build_blank_template, decode_signature_png, fill_and_sign
from app.forms.models import BrokerageAuthorizationPayload, CleanSignaturePhotoPayload
from app.forms.page import CLEAN_SIGNATURE_PATH, FORM_PATH, TEMPLATE_PATH_URL, render_form_html
from app.forms.rate_limit import rate_limit
from app.forms.signature_cleaner import clean_signature_photo

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


def _pdf_field_values(payload: BrokerageAuthorizationPayload) -> dict[str, str]:
    """`model_dump()` trae ints/None (sale_price, outstanding_debt, term_months) y
    "si"/"no" (mortgage_loan, leasing) — el AcroForm solo acepta texto."""
    values = payload.model_dump(exclude={"signature_png"})
    values["mortgage_loan"] = _YES_NO_LABELS[values["mortgage_loan"]]
    values["leasing"] = _YES_NO_LABELS[values["leasing"]]
    return {key: ("" if value is None else str(value)) for key, value in values.items()}


def _decode_image_data_url_or_400(data_url: str) -> bytes:
    try:
        return decode_signature_png(data_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _content_disposition(filename: str) -> str:
    """Nombre de archivo "normal" (con espacios/acentos) para lo que el usuario descarga.

    La URL sigue en minúsculas y con guiones (convención web); el nombre del
    archivo descargado es aparte y va legible tal como lo vería el usuario
    en su explorador de archivos. `filename*` (RFC 5987) lleva los acentos;
    `filename` es el fallback ASCII para navegadores viejos.
    """
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get(
    FORM_PATH,
    response_class=HTMLResponse,
    summary="Formulario de Autorización de Corretaje (llenar y firmar desde el celular)",
)
def get_brokerage_authorization_form(deal_id: str | None = None) -> HTMLResponse:
    return HTMLResponse(render_form_html(deal_id=deal_id))


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
    summary="Descarga la plantilla del AcroForm sin diligenciar (para pruebas)",
)
def get_brokerage_authorization_template() -> Response:
    return Response(
        content=build_blank_template(),
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition("Autorización de Corretaje - Plantilla.pdf")},
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

    signature_png_bytes = _decode_image_data_url_or_400(payload.signature_png)

    values = _pdf_field_values(payload)

    try:
        pdf_bytes = fill_and_sign(values, signature_png_bytes)
    except Exception:
        logger.exception("Error generando el PDF de Autorización de Corretaje")
        raise HTTPException(status_code=500, detail="No se pudo generar el documento.") from None

    if payload.deal_id:
        _add_signed_authorization_comment(payload.deal_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition("Autorización de Corretaje - Firmada.pdf")},
    )


def _add_signed_authorization_comment(deal_id: str) -> None:
    """Deja constancia en el timeline del deal de que el cliente firmó. Best-effort: nunca rompe la descarga del PDF."""
    try:
        bitrix_client = get_bitrix_client()
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        bitrix_client.add_comment(deal_id, "deal", f"El cliente firmó la Autorización de Corretaje el {fecha}.")
    except Exception:
        logger.exception("Error dejando comentario de firma en el deal %s", deal_id)
