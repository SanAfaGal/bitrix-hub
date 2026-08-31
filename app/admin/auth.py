"""Login del panel admin: usuario/clave único compartido, sesión en cookie firmada.

La cookie la firma/verifica `SessionMiddleware` (Starlette, agregado en
`app/main.py` con `ADMIN_SESSION_SECRET`) — acá solo se compara la
credencial y se marca/lee la sesión (`request.session`).
"""
from __future__ import annotations

import hmac

from fastapi import Request

from app.admin.settings import load_admin_settings

_SESSION_KEY = "admin_username"


def verify_credentials(username: str, password: str) -> bool:
    """Compara contra el usuario/clave único configurado, en tiempo constante."""
    settings = load_admin_settings()
    return hmac.compare_digest(username, settings.username) and hmac.compare_digest(password, settings.password)


def log_in(request: Request, username: str) -> None:
    request.session[_SESSION_KEY] = username


def log_out(request: Request) -> None:
    request.session.pop(_SESSION_KEY, None)


def current_admin(request: Request) -> str | None:
    """Retorna el usuario logueado, o None si no hay sesión activa."""
    username = request.session.get(_SESSION_KEY)
    return username if isinstance(username, str) and username else None
