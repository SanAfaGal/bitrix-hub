"""Configuración de variables de entorno para el login corporativo (Microsoft Entra ID)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class SessionSettings:
    """Secreto de la cookie de sesión, compartido por todo el staff (interno + admin).

    Antes vivía en app/admin/settings.py como ADMIN_SESSION_SECRET — un solo
    login corporativo para todo el staff ya no justifica que el secreto de
    sesión sea "del admin".
    """

    secret: str
    https_only: bool = True


@dataclass(frozen=True)
class MicrosoftOAuthSettings:
    tenant_id: str
    client_id: str
    client_secret: str
    public_base_url: str
    allowed_domains: tuple[str, ...] = ()
    admin_emails: tuple[str, ...] = ()


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip().lower() for part in value.split(",") if part.strip())


def load_session_settings() -> SessionSettings:
    """Se carga al arrancar la app (`app/main.py`) — falla duro si falta el secreto,
    igual que antes con ADMIN_SESSION_SECRET (mismo motivo: firmar cookies con un
    secreto público/por defecto permitiría forjar sesión de staff sin login)."""
    load_dotenv()

    secret = (os.getenv("SESSION_SECRET_KEY") or "").strip()
    https_only = (os.getenv("SESSION_HTTPS_ONLY") or "true").strip().lower() not in ("0", "false", "no")

    if not secret:
        raise RuntimeError("Falta variable de entorno: SESSION_SECRET_KEY")

    return SessionSettings(secret=secret, https_only=https_only)


def load_microsoft_oauth_settings() -> MicrosoftOAuthSettings:
    """Se carga perezosamente (solo cuando alguien intenta iniciar sesión), no al
    arrancar la app — así el resto del hub sigue funcionando aunque el login
    corporativo todavía no esté configurado en este despliegue."""
    load_dotenv()

    tenant_id = (os.getenv("MS_OAUTH_TENANT_ID") or "").strip()
    client_id = (os.getenv("MS_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("MS_OAUTH_CLIENT_SECRET") or "").strip()
    public_base_url = (os.getenv("HUB_PUBLIC_BASE_URL") or "").strip().rstrip("/")

    missing = [
        name
        for name, value in (
            ("MS_OAUTH_TENANT_ID", tenant_id),
            ("MS_OAUTH_CLIENT_ID", client_id),
            ("MS_OAUTH_CLIENT_SECRET", client_secret),
            ("HUB_PUBLIC_BASE_URL", public_base_url),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Faltan variables de entorno: " + ", ".join(missing))

    return MicrosoftOAuthSettings(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        public_base_url=public_base_url,
        allowed_domains=_split_csv(os.getenv("ALLOWED_EMAIL_DOMAINS")),
        admin_emails=_split_csv(os.getenv("ADMIN_EMAILS")),
    )
