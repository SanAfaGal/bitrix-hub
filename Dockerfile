FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app migrations ./migrations

USER app

EXPOSE 8000

# El contenedor NUNCA corre migraciones solo — ni acá ni en desarrollo
# (docker-compose.override.yml) se auto-aplican contra producción. `alembic
# upgrade head` en prod es un paso manual y deliberado del operador (ver
# README, sección de despliegue) — `alembic.ini`/`migrations/` quedan en la
# imagen solo para poder correrlo con `docker compose exec api alembic
# upgrade head`, nunca al arrancar.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
