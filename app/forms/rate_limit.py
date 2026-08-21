"""Rate limiting simple en memoria para los endpoints públicos de formularios.

Sin dependencia nueva (no hace falta slowapi/redis para un solo proceso):
ventana deslizante por IP + nombre de endpoint, guardada en un dict con lock.
No sobrevive un restart ni se comparte entre réplicas — si el hub llega a
correr con más de un worker/instancia, esto hay que moverlo a algo compartido
(Redis). Para un solo contenedor alcanza como mitigación de abuso.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, key: str, *, max_requests: int, window_seconds: float) -> None:
    client_ip = request.client.host if request.client else "unknown"
    bucket_key = f"{key}:{client_ip}"
    now = time.monotonic()

    with _lock:
        hits = _hits[bucket_key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail="Demasiadas solicitudes. Espera un minuto e intenta de nuevo.",
            )
        hits.append(now)
