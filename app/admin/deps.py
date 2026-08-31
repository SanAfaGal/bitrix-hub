"""Dependencia de FastAPI para proteger las rutas del panel admin."""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.admin.auth import current_admin


def require_login(request: Request) -> str:
    """Retorna el usuario logueado, o redirige a /admin/login (303) si no hay sesión."""
    username = current_admin(request)
    if username is None:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return username
