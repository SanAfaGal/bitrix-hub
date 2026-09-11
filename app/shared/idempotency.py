"""Idempotencia simple en memoria, para formularios que crean algo al hacer POST.

Mismo espíritu que `app/shared/rate_limit.py`: sin dependencia nueva (no hace
falta Redis para un solo proceso), un dict con lock. No sobrevive un restart
ni se comparte entre réplicas — igual que rate_limit, si el hub llega a correr
con más de un worker/instancia, esto hay que moverlo a algo compartido.

Uso: `new_token()` al servir el GET del formulario (se manda como campo oculto);
`consume(token)` al recibir el POST — la primera vez marca el token como usado
y retorna True (seguir con la creación); las siguientes retornan False (no
crear de nuevo, es un reenvío/doble clic del mismo formulario).
"""
from __future__ import annotations

import time
import uuid
from threading import Lock

_lock = Lock()
_used_tokens: dict[str, float] = {}

# Un formulario no debería tardar más que esto entre servir el GET y recibir
# el POST — pasado este tiempo se limpia para no acumular memoria indefinida.
_TOKEN_TTL_SECONDS = 3600.0


def new_token() -> str:
    return uuid.uuid4().hex


def _evict_expired(now: float) -> None:
    expired = [token for token, used_at in _used_tokens.items() if now - used_at > _TOKEN_TTL_SECONDS]
    for token in expired:
        del _used_tokens[token]


def consume(token: str) -> bool:
    """Retorna True la primera vez que se ve `token` (seguir), False si ya se usó
    (reenvío — no repetir la creación)."""
    now = time.monotonic()
    with _lock:
        _evict_expired(now)
        if token in _used_tokens:
            return False
        _used_tokens[token] = now
        return True
