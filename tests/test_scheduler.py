from __future__ import annotations

import app.scheduler as scheduler_module
from app.location_catalog.sector_sync import SyncSummary


def test_job_process_leads_logs_and_returns_when_config_missing(monkeypatch, caplog) -> None:
    def _raise():
        raise RuntimeError("Faltan variables de entorno: GRAPH_TENANT_ID")

    monkeypatch.setattr(scheduler_module, "load_graph_settings", _raise)

    with caplog.at_level("ERROR"):
        scheduler_module.job_process_leads()

    assert "se omite esta corrida" in caplog.text


def test_job_process_leads_calls_process_inbox_and_logs_summary(monkeypatch, caplog) -> None:
    monkeypatch.setattr(scheduler_module, "load_graph_settings", lambda: ("t", "c", "s", "mailbox@example.com"))
    monkeypatch.setattr(scheduler_module, "get_crm_client", lambda: object())

    summary = {"created": [{"deal_id": "1"}], "skipped": [], "errors": [], "already_processed": []}
    monkeypatch.setattr(scheduler_module, "process_inbox", lambda graph_client, crm_client, **kw: summary)

    with caplog.at_level("INFO"):
        scheduler_module.job_process_leads()

    assert "1 creados" in caplog.text


def test_job_sync_sectores_logs_and_returns_when_config_missing(monkeypatch, caplog) -> None:
    def _raise():
        raise RuntimeError("Falta variable de entorno: BITRIX_WEBHOOK_URL")

    monkeypatch.setattr(scheduler_module, "load_bitrix_settings", _raise)

    with caplog.at_level("ERROR"):
        scheduler_module.job_sync_sectores()

    assert "se omite esta corrida" in caplog.text


def test_job_sync_sectores_calls_run_sync_and_logs_summary(monkeypatch, caplog) -> None:
    monkeypatch.setattr(scheduler_module, "load_bitrix_settings", lambda: "https://example.bitrix24.com/rest/1/token/")
    summary = SyncSummary(total_source=10, created=2, updated=1, unchanged=7)
    monkeypatch.setattr(scheduler_module, "run_sync", lambda client, dry_run: summary)

    with caplog.at_level("INFO"):
        scheduler_module.job_sync_sectores()

    assert "2 creados" in caplog.text


def test_start_scheduler_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    assert scheduler_module.start_scheduler() is None


def test_start_scheduler_schedules_both_jobs_with_configured_intervals(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("GRAPH_LEAD_POLL_MINUTES", "5")
    monkeypatch.setenv("SECTOR_SYNC_INTERVAL_DAYS", "7")

    scheduler = scheduler_module.start_scheduler()
    try:
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert set(jobs) == {"graph_process_leads", "sector_sync"}
    finally:
        scheduler.shutdown(wait=False)
