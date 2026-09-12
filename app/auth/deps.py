"""Dependencias de FastAPI para proteger rutas con login corporativo."""
from __future__ import annotations

from fastapi import HTTPException, Request

_SESSION_KEY = "staff_user"


def current_staff_user(request: Request) -> dict[str, str] | None:
    """Retorna `{"name":..., "email":...}`, o None si no hay sesión activa."""
    user = request.session.get(_SESSION_KEY)
    if isinstance(user, dict) and user.get("email"):
        return user
    return None


def log_in(request: Request, *, name: str, email: str) -> None:
    request.session[_SESSION_KEY] = {"name": name, "email": email}


def log_out(request: Request) -> None:
    request.session.pop(_SESSION_KEY, None)


def require_staff_user(request: Request) -> dict[str, str]:
    """Cualquier cuenta corporativa autenticada — usada por `/interno/...`.

    Redirige (303) a `/auth/login` en vez de un 401 crudo: quien llega sin
    sesión a una página que se navega con el navegador debe terminar en la
    pantalla de login, no en un error de API.
    """
    user = current_staff_user(request)
    if user is None:
        next_url = request.url.path
        raise HTTPException(status_code=303, headers={"Location": f"/auth/login?next={next_url}"})
    return user


def is_admin_email(email: str) -> bool:
    """Chequeo sin levantar excepción, para decidir qué mostrar en la UI (ej. si
    aparece el enlace al panel admin en la navegación) — a diferencia de
    `require_admin`, que sí es la puerta que protege las rutas. `ADMIN_EMAILS`
    puede no estar configurado en este despliegue; en ese caso, no admin."""
    from app.auth.settings import load_microsoft_oauth_settings

    try:
        settings = load_microsoft_oauth_settings()
    except RuntimeError:
        return False
    return email.lower() in settings.admin_emails


def require_admin(request: Request) -> str:
    """Cuenta corporativa autenticada Y en `ADMIN_EMAILS` — reemplaza el login por
    credencial única que tenía el panel admin. Depende de `require_staff_user` (no
    de un chequeo de sesión crudo) para que alguien sin sesión reciba el redirect a
    login en vez de un 403 directo.

    Retorna el email (antes retornaba el `username` de la credencial única) — se
    usa igual en los templates del panel admin, solo cambia qué identifica al
    usuario logueado.
    """
    from app.auth.settings import load_microsoft_oauth_settings

    user = require_staff_user(request)
    try:
        settings = load_microsoft_oauth_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if user["email"].lower() not in settings.admin_emails:
        raise HTTPException(status_code=403, detail="Tu cuenta no tiene acceso al panel admin.")
    return user["email"]
