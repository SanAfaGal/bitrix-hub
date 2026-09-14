"""Jobs programados dentro del propio proceso.

Sin esto, "correos nuevos -> Bitrix" (`app/flows/graph_lead_intake.py`) y
"sectores Mobilia -> Bitrix" (`app/location_catalog/sector_sync.py`) solo
corren cuando alguien los dispara a mano (`POST /graph/process-leads` o
`scripts/sync_mobilia_sectores.py`).

No es un paquete de integración (no representa un sistema externo, ver
CLAUDE.md) — vive a este nivel, igual que `app/main.py`, porque orquesta
jobs que ya de por sí cruzan integraciones (Graph+CRM, Mobilia+Bitrix).
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from app.bitrix.client import BitrixClient
from app.bitrix.settings import load_bitrix_settings
from app.crm.deps import get_crm_client
from app.flows.graph_lead_intake import process_inbox
from app.graph.client import GraphClient
from app.graph.settings import load_graph_settings
from app.location_catalog.sector_sync import run_sync

logger = logging.getLogger(__name__)

_JOB_ID_PROCESS_LEADS = "graph_process_leads"
_JOB_ID_SECTOR_SYNC = "sector_sync"

_DEFAULT_GRAPH_LEAD_POLL_MINUTES = 5
_DEFAULT_SECTOR_SYNC_INTERVAL_DAYS = 7


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes")


def job_process_leads() -> None:
    """Revisa el inbox y crea lo que falte en Bitrix (ver `process_inbox`).

    Nunca deja escapar una excepción: un job de APScheduler que revienta
    queda desprogramado silenciosamente — más simple loguear acá y dejar
    que la siguiente corrida (unos minutos después) lo intente de nuevo.
    """
    try:
        tenant_id, client_id, client_secret, mailbox = load_graph_settings()
        graph_client = GraphClient(tenant_id, client_id, client_secret, mailbox)
        crm_client = get_crm_client()
    except Exception:
        logger.exception("No se pudo armar los clientes para el job de correos, se omite esta corrida")
        return

    try:
        summary = process_inbox(graph_client, crm_client)
    except Exception:
        logger.exception("Job de correos (process_inbox) falló")
        return

    logger.info(
        "Job de correos: %d creados, %d omitidos, %d errores, %d ya procesados",
        len(summary["created"]),
        len(summary["skipped"]),
        len(summary["errors"]),
        len(summary["already_processed"]),
    )


def job_sync_sectores() -> None:
    """Sincroniza el catálogo de sectores de Mobilia hacia Bitrix (ver `run_sync`)."""
    try:
        client = BitrixClient(load_bitrix_settings())
    except Exception:
        logger.exception("No se pudo armar el cliente de Bitrix para el job de sectores, se omite esta corrida")
        return

    try:
        summary = run_sync(client, dry_run=False)
    except Exception:
        logger.exception("Job de sincronización de sectores falló")
        return

    logger.info(
        "Job de sectores: %d creados, %d actualizados, %d sin cambios, %d errores",
        summary.created,
        summary.updated,
        summary.unchanged,
        len(summary.errors),
    )


def start_scheduler() -> BackgroundScheduler | None:
    """Arranca el scheduler en background — llamar una sola vez, desde el lifespan de `app/main.py`.

    `SCHEDULER_ENABLED=false` lo apaga por completo (desarrollo local sin
    credenciales de Graph/Mobilia configuradas, o tests). Intervalos
    configurables por `.env`: `GRAPH_LEAD_POLL_MINUTES` (default 5) y
    `SECTOR_SYNC_INTERVAL_DAYS` (default 7) — los sectores cambian mucho
    menos seguido que los correos, no tiene sentido revisarlos con la misma
    frecuencia.
    """
    load_dotenv()
    if not _env_bool("SCHEDULER_ENABLED", default=True):
        logger.info("Scheduler deshabilitado (SCHEDULER_ENABLED=false)")
        return None

    poll_minutes = _env_int("GRAPH_LEAD_POLL_MINUTES", _DEFAULT_GRAPH_LEAD_POLL_MINUTES)
    sync_days = _env_int("SECTOR_SYNC_INTERVAL_DAYS", _DEFAULT_SECTOR_SYNC_INTERVAL_DAYS)

    scheduler = BackgroundScheduler(timezone="America/Bogota")
    scheduler.add_job(
        job_process_leads,
        IntervalTrigger(minutes=poll_minutes),
        id=_JOB_ID_PROCESS_LEADS,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_sync_sectores,
        IntervalTrigger(days=sync_days),
        id=_JOB_ID_SECTOR_SYNC,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado: correos cada %d min, sectores cada %d días", poll_minutes, sync_days)
    return scheduler
