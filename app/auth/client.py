"""Inicio de sesión con Microsoft Entra ID (Azure AD) — adaptado de flash-view.

Igual que flash-view: flujo OAuth2 authorization-code artesanal (sin
MSAL/authlib) contra una app registration single-tenant — la pertenencia al
tenant la impone Microsoft en el propio intercambio de token, no una
inspección de claims acá. La identidad se confirma con una llamada a
Microsoft Graph `/me`, nunca parseando el JWT.

Diferencia con flash-view: acá es síncrono (`requests`, no `httpx.AsyncClient`)
para seguir el estilo del resto del hub (todos los routers son `def`, no
`async def` — ver app/xposure/client.py, app/waha/client.py).
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
SCOPE = "openid profile email User.Read"
REQUEST_TIMEOUT = 15


class MicrosoftAuthError(Exception):
    """Se lanza cuando el login con Microsoft falla en cualquier paso (intercambio de
    token, consulta de perfil, o dominio no permitido)."""


def build_authorize_url(*, tenant_id: str, client_id: str, redirect_uri: str, state: str) -> str:
    """`prompt=select_account` obliga a Microsoft a mostrar su selector de cuentas
    incluso con una sesión SSO activa — si no, reautentica en silencio con la
    última cuenta usada y la persona nunca puede cambiar de cuenta en un equipo
    compartido."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": SCOPE,
        "state": state,
        "prompt": "select_account",
    }
    authority = AUTHORITY_TEMPLATE.format(tenant_id=tenant_id)
    return f"{authority}/oauth2/v2.0/authorize?{urlencode(params)}"


def build_logout_url(*, tenant_id: str, post_logout_redirect_uri: str) -> str:
    """Termina también la sesión SSO de Microsoft — si no, un "cerrar sesión" solo
    limpia la cookie local y el próximo login reautentica en silencio la misma cuenta."""
    params = {"post_logout_redirect_uri": post_logout_redirect_uri}
    authority = AUTHORITY_TEMPLATE.format(tenant_id=tenant_id)
    return f"{authority}/oauth2/v2.0/logout?{urlencode(params)}"


def exchange_code_for_token(
    *, tenant_id: str, client_id: str, client_secret: str, redirect_uri: str, code: str
) -> str:
    """Intercambia un authorization code por un access token — se usa una sola vez
    (para llamar a Graph `/me`), nunca se persiste."""
    authority = AUTHORITY_TEMPLATE.format(tenant_id=tenant_id)
    try:
        response = requests.post(
            f"{authority}/oauth2/v2.0/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "scope": SCOPE,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Fallo el intercambio de token con Microsoft")
        raise MicrosoftAuthError("No se pudo iniciar sesión con Microsoft") from None

    body = response.json()
    access_token = body.get("access_token")
    if not access_token:
        logger.warning("Respuesta de token de Microsoft sin access_token: %s", body)
        raise MicrosoftAuthError("No se pudo iniciar sesión con Microsoft")
    return access_token


def fetch_user_profile(access_token: str) -> dict[str, str]:
    """Confirma la identidad vía Microsoft Graph. Devuelve `{"name":..., "email":...}`
    — `email` es `mail` si está seteado, si no `userPrincipalName` (siempre presente
    en cuentas de trabajo/escolares)."""
    try:
        response = requests.get(
            GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "displayName,mail,userPrincipalName"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Fallo la consulta a Microsoft Graph /me")
        raise MicrosoftAuthError("No se pudo confirmar tu cuenta de Microsoft") from None

    body: dict[str, Any] = response.json()
    email = body.get("mail") or body.get("userPrincipalName")
    if not email:
        logger.warning("Microsoft Graph /me sin mail/userPrincipalName: %s", body)
        raise MicrosoftAuthError("No se pudo confirmar tu cuenta de Microsoft")

    name = body.get("displayName") or email
    return {"name": name, "email": email}


def check_allowed_domain(email: str, allowed_domains: tuple[str, ...]) -> None:
    """Defensa en profundidad sobre la restricción de tenant. No hace nada si
    `allowed_domains` está vacío — la app registration single-tenant queda como
    la única restricción."""
    if not allowed_domains:
        return
    domain = email.rsplit("@", 1)[-1].lower()
    if domain not in allowed_domains:
        logger.warning("Login de Microsoft rechazado por dominio no permitido: %s", email)
        raise MicrosoftAuthError("Esta cuenta de Microsoft no tiene acceso a este sistema")
