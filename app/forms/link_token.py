"""Firma del `deal_id` que va en el link del formulario, enviado por WhatsApp.

Evita que alguien adivine o itere `deal_id` en la URL para abrir el
formulario de otro deal: el link válido lleva también un token HMAC del
`deal_id`, calculado con un secreto que solo conoce este servidor. Sin
expiración a propósito (el cliente puede retomar el mismo link días
después) — lo que bloquea el reenvío una vez firmado es el estado del
deal en Bitrix, no la caducidad del token (ver `app/forms/router.py`).
"""
from __future__ import annotations

import hashlib
import hmac


def sign_deal_id(deal_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), deal_id.encode(), hashlib.sha256).hexdigest()


def verify_deal_id_token(deal_id: str, token: str | None, secret: str) -> bool:
    if not token:
        return False
    expected = sign_deal_id(deal_id, secret)
    return hmac.compare_digest(expected, token)
