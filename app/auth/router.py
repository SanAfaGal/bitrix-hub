"""Login corporativo (Microsoft Entra ID) — único punto de login para todo el staff."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth.client import (
    MicrosoftAuthError,
    build_authorize_url,
    build_logout_url,
    check_allowed_domain,
    exchange_code_for_token,
    fetch_user_profile,
)
from app.auth.deps import log_in, log_out
from app.auth.settings import load_microsoft_oauth_settings
from app.shared.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

_LOGIN_RATE_LIMIT = {"max_requests": 10, "window_seconds": 60}
_CALLBACK_RATE_LIMIT = {"max_requests": 10, "window_seconds": 60}

# A dónde vuelve alguien que no vino de ningún /interno/... en particular
# (ej. entró directo a /auth/login).
_DEFAULT_NEXT = "/interno/nuevo-lead"


def _redirect_uri(public_base_url: str) -> str:
    return f"{public_base_url}/auth/callback"


def _safe_next(next_url: str | None) -> str:
    """Solo rutas propias — evita usar `next` como open redirect a un dominio externo."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return _DEFAULT_NEXT


@router.get("/login", summary="Inicia el login corporativo (Microsoft Entra ID)")
def get_login(request: Request, next: str | None = None) -> RedirectResponse:
    rate_limit(request, "auth-login", **_LOGIN_RATE_LIMIT)
    try:
        settings = load_microsoft_oauth_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = _safe_next(next)

    url = build_authorize_url(
        tenant_id=settings.tenant_id,
        client_id=settings.client_id,
        redirect_uri=_redirect_uri(settings.public_base_url),
        state=state,
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback", summary="Callback de Microsoft tras el login")
def get_callback(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    rate_limit(request, "auth-callback", **_CALLBACK_RATE_LIMIT)

    expected_state = request.session.pop("oauth_state", None)
    next_url = _safe_next(request.session.pop("oauth_next", None))

    if not code or not state or not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Respuesta de inicio de sesión inválida.")

    try:
        settings = load_microsoft_oauth_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        access_token = exchange_code_for_token(
            tenant_id=settings.tenant_id,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            redirect_uri=_redirect_uri(settings.public_base_url),
            code=code,
        )
        profile = fetch_user_profile(access_token)
        check_allowed_domain(profile["email"], settings.allowed_domains)
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_in(request, name=profile["name"], email=profile["email"])
    return RedirectResponse(url=next_url, status_code=302)


@router.post("/logout", summary="Cierra la sesión corporativa")
def post_logout(request: Request) -> RedirectResponse:
    log_out(request)
    try:
        settings = load_microsoft_oauth_settings()
    except RuntimeError:
        return RedirectResponse(url="/auth/login", status_code=303)

    url = build_logout_url(
        tenant_id=settings.tenant_id,
        post_logout_redirect_uri=f"{settings.public_base_url}/auth/login",
    )
    return RedirectResponse(url=url, status_code=302)
