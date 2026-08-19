# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FastAPI service that receives Bitrix webhooks and dispatches actions to external systems: property lookups in Xposure (migrated from the separate `MLS` repo) and WhatsApp sends via Waha (self-hosted, runs as a second service in this same `docker-compose.yml` — not a separate repo). One deploy, one `.env`, modular by integration internally.

`MLS` (`../Ventas/MLS`) is still the live production service until the Bitrix automation rule is repointed to this hub's `/webhook/deal-event` — see "Corte de producción pendiente" in README.md before assuming this repo is already receiving real traffic.

## Commands

```bash
uv sync                                    # install deps
uv run uvicorn app.main:app --reload       # run API locally (needs Waha reachable, see below)
uv run python -m pytest -q                 # run all tests
uv run python -m pytest tests/test_waha_client.py -q          # single test file
uv run python -m pytest tests/test_waha_client.py::test_name  # single test

docker compose up -d --build               # api + waha, dev override auto-loads (hot-reload, no rebuild on code change)
docker compose -f docker-compose.yml up -d # prod: same stack, no hot-reload override
```

`WAHA_BASE_URL` in `.env` is set to `http://waha:3000` (Docker-network hostname, works when both services run via `docker compose`). Running the API bare with `uv run uvicorn` outside Docker, override it inline without touching `.env`: `WAHA_BASE_URL=http://localhost:3000 uv run uvicorn app.main:app --reload` (works because `load_dotenv()` never overrides a variable already set in the shell).

## Architecture

**Integration packages, not a flat app.** Each external system gets its own package under `app/`: `app/bitrix/` (core, shared by everyone), `app/xposure/`, `app/waha/`. Inside each: `client.py` (HTTP client, never raises on network failure — logs and returns `None`/`False`/`{}`), `settings.py` (env var loading), `router.py` (FastAPI `APIRouter`, tagged), `deps.py` (dependency-provider functions consumed via `Depends(...)`; client-construction errors are caught here and re-raised as `HTTPException` so routes don't repeat that try/except).

**One webhook endpoint per Bitrix trigger, no generic rule engine.** Bitrix's own automation config already decides what fires when; each automation rule points at its own URL here. Don't build a dispatcher — add a new route instead.

**Flows that touch more than one integration live in `app/flows/`, not inside an integration package.** Integration packages never import each other. A multi-integration flow (e.g. `app/flows/deal_duplicado.py`: Bitrix + Xposure) is a plain function that takes already-constructed clients as arguments; its `router.py` in the same directory wires the actual Bitrix-facing endpoint. See `app/flows/README.md` for the expected shape of a new one.

**`app/main.py` only assembles**: creates the `FastAPI()` app, sets `openapi_tags`, calls `app.include_router(...)` for each package's router, and owns `/health`. No business-logic endpoints belong there.

**Testing routes that use `Depends(get_x_client)`**: use `app.dependency_overrides[get_x_client] = lambda: FakeClient()` (clear it in a `finally`), not `monkeypatch.setattr(...)` — `Depends` captures the function object at route-definition time, so patching the module attribute afterward has no effect. Plain function calls that aren't wrapped in `Depends` (e.g. in `app/flows/router.py`, which calls `get_bitrix_client()`/`get_xposure_client()` directly rather than via dependency injection, so `get_xposure_client` can be created lazily only if actually needed) can still be monkeypatched by module path — see `tests/test_main.py` for both patterns side by side.

**Adding a new integration**: `client.py` + `settings.py` in a new `app/<name>/` package; business rules go in `app/<name>/events.py` if they only touch that integration, or in `app/flows/<name>.py` if they combine it with another. For Mobilia ERP specifically, don't write a client from scratch — reuse the existing [`mobilia-erp-client`](https://github.com/albertoalvarez/mobilia-erp-client) package as a dependency.

**Phone numbers from Bitrix are messy** (`app/waha/phone.py`): Bitrix stores phone as a `PHONE` array on the *contact*, not a plain field on the deal (`BitrixClient.get_contact()` fetches it). `extract_phone_from_contact()` picks the best entry (prefers `MOBILE`); `to_chat_id()` strips formatting, keeps the country code (drops only the `+`/`00` prefix marker), and defaults to `57` (Colombia) only for bare 10-digit local numbers — it returns `None` rather than guessing on anything ambiguous.

**Resource limits and dev/prod split**: `docker-compose.yml` carries prod-shaped defaults (`restart: unless-stopped`, `deploy.resources.limits` sized from `.env`, healthchecks, `security_opt`). `docker-compose.override.yml` is dev-only and auto-loads with plain `docker compose up` (mounts `./app`, adds `--reload`); production runs explicitly without it.

## Full details

`README.md` has the complete endpoint list (with curl examples), the full `.env` variable reference (Waha engine/TZ/logging/dashboard config lives there now, not hardcoded in any compose file), and the pending MLS→bitrix-hub cutover checklist.
