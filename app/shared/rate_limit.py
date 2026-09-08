"""Rate limiting simple en memoria: no es específico de ningún endpoint/paquete.

Sin dependencia nueva (no hace falta slowapi/redis para un solo proceso):
ventana deslizante por IP + nombre de bucket, guardada en un dict con lock.
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


def _client_ip(request: Request) -> str:
    """En producción el tráfico externo pasa por un reverse proxy delante del contenedor
    `api` (ver docker-compose.yml) — sin esto, `request.client.host` sería siempre la IP
    interna del proxy para todas las solicitudes, y el rate limit terminaría siendo un
    límite global compartido por todos los visitantes en vez de uno por cliente real.
    `X-Forwarded-For` puede traer varias IPs separadas por coma (una por proxy
    intermedio); la primera es la del cliente original."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, key: str, *, max_requests: int, window_seconds: float) -> None:
    client_ip = _client_ip(request)
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
