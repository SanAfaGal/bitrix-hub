"""Login corporativo (Microsoft Entra ID) para todo el staff.

Autenticación (`require_staff_user`) separada de autorización
(`require_admin`, que además exige `ADMIN_EMAILS`) — ver `deps.py`. Único
punto de login: `/auth/login`, `/auth/callback`, `/auth/logout`.
"""
