from __future__ import annotations

from app.bitrix import fields
from app.bitrix.client_sectors import BatchUpsertResult
from app.location_catalog import sector_sync
from app.location_catalog.client import Sector


def _sector(sector_code: str, sector: str = "El Poblado", zona: str = "Sur", ciudad: str = "Medellín") -> Sector:
    return Sector(
        sector_code=sector_code,
        sector=sector,
        zona=zona,
        ciudad=ciudad,
        departamento="Antioquia",
        pais="Colombia",
        cobertura=True,
    )


class FakeSectorsBitrixClient:
    def __init__(
        self,
        existing_by_code: dict[str, dict] | None = None,
        batch_result: BatchUpsertResult | None = None,
    ) -> None:
        self._existing_by_code = existing_by_code if existing_by_code is not None else {}
        self._batch_result = batch_result if batch_result is not None else BatchUpsertResult()
        self.batch_calls: list[tuple[dict, dict]] = []
        self.list_calls = 0

    def list_sector_items(self):
        self.list_calls += 1
        return self._existing_by_code

    def batch_upsert_sector_items(self, creates, updates):
        self.batch_calls.append((creates, updates))
        return self._batch_result


# --- dedupe_source ---


def test_dedupe_source_keeps_unique_codes() -> None:
    sectores = [_sector("1"), _sector("2")]
    deduped, duplicates = sector_sync.dedupe_source(sectores)
    assert deduped == sectores
    assert duplicates == []


def test_dedupe_source_excludes_all_copies_of_a_duplicate_code() -> None:
    sectores = [_sector("1"), _sector("1", sector="Otro nombre"), _sector("2")]
    deduped, duplicates = sector_sync.dedupe_source(sectores)
    assert deduped == [_sector("2")]
    assert duplicates == ["1"]


# --- build_target_fields ---


def test_build_target_fields_uses_build_location_label_for_ubicacion() -> None:
    sector = _sector("1")
    target = sector_sync.build_target_fields(sector)
    assert target[fields.FIELD_SECTOR_UBICACION.uf_crm] == "El Poblado, Sur, Medellín, Antioquia, Colombia"


def test_build_target_fields_never_sends_title() -> None:
    """Bitrix ya tiene una regla de automatización que arma TITLE concatenando
    campos existentes del ítem — mandar TITLE desde acá lo pisaría."""
    sector = _sector("1")
    target = sector_sync.build_target_fields(sector)
    assert "TITLE" not in target


def test_build_target_fields_includes_business_key_field() -> None:
    sector = _sector("00083")
    target = sector_sync.build_target_fields(sector)
    assert target[fields.FIELD_SECTOR_CODE.uf_crm] == "00083"


# --- needs_update ---


def test_needs_update_false_when_values_match() -> None:
    target = {fields.FIELD_SECTOR_UBICACION.uf_crm: "El Poblado"}
    existing = {"title": "El Poblado", fields.FIELD_SECTOR_UBICACION.uf_crm: "El Poblado"}
    assert sector_sync.needs_update(existing, target) is False


def test_needs_update_ignores_title() -> None:
    """TITLE lo arma una regla de automatización de Bitrix (concatena campos
    del ítem), no se manda desde acá ni participa en la comparación —
    comparar por TITLE rompería la idempotencia si esa regla lo reescribe."""
    target = {fields.FIELD_SECTOR_UBICACION.uf_crm: "El Poblado"}
    existing = {"title": "678 - El Poblado", fields.FIELD_SECTOR_UBICACION.uf_crm: "El Poblado"}
    assert sector_sync.needs_update(existing, target) is False


def test_needs_update_true_when_ubicacion_differs() -> None:
    target = {fields.FIELD_SECTOR_UBICACION.uf_crm: "El Poblado Nuevo"}
    existing = {"title": "El Poblado", fields.FIELD_SECTOR_UBICACION.uf_crm: "El Poblado"}
    assert sector_sync.needs_update(existing, target) is True


# --- plan_sync ---


def test_plan_sync_detects_new_sector() -> None:
    sector = _sector("1")
    to_create, to_update, unchanged = sector_sync.plan_sync([sector], {})
    assert to_create == [sector]
    assert to_update == []
    assert unchanged == []


def test_plan_sync_detects_existing_unchanged_sector() -> None:
    sector = _sector("1")
    target = sector_sync.build_target_fields(sector)
    existing_by_code = {"1": {"id": "50", "title": "678 - lo que sea", fields.FIELD_SECTOR_UBICACION.uf_crm: target[fields.FIELD_SECTOR_UBICACION.uf_crm]}}
    to_create, to_update, unchanged = sector_sync.plan_sync([sector], existing_by_code)
    assert to_create == []
    assert to_update == []
    assert unchanged == ["1"]


def test_plan_sync_detects_existing_changed_sector() -> None:
    sector = _sector("1")
    existing_by_code = {"1": {"id": "50", "title": "Nombre viejo", fields.FIELD_SECTOR_UBICACION.uf_crm: "Nombre viejo"}}
    to_create, to_update, unchanged = sector_sync.plan_sync([sector], existing_by_code)
    assert to_create == []
    assert to_update == [("50", sector)]
    assert unchanged == []


# --- run_sync ---


def test_run_sync_creates_new_sectors(monkeypatch) -> None:
    sector = _sector("1")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector])
    batch_result = BatchUpsertResult(succeeded_creates={"create_1": "999"})
    client = FakeSectorsBitrixClient(existing_by_code={}, batch_result=batch_result)

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.total_source == 1
    assert summary.created == 1
    assert summary.updated == 0
    assert summary.unchanged == 0
    assert summary.errors == []
    creates, updates = client.batch_calls[0]
    assert list(creates) == ["create_1"]
    assert updates == {}


def test_run_sync_updates_changed_sectors(monkeypatch) -> None:
    sector = _sector("1")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector])
    existing_by_code = {"1": {"id": "50", "title": "Nombre viejo", fields.FIELD_SECTOR_UBICACION.uf_crm: "Nombre viejo"}}
    batch_result = BatchUpsertResult(succeeded_updates={"update_1"})
    client = FakeSectorsBitrixClient(existing_by_code=existing_by_code, batch_result=batch_result)

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.created == 0
    assert summary.updated == 1
    assert summary.unchanged == 0
    assert summary.errors == []
    creates, updates = client.batch_calls[0]
    assert creates == {}
    assert list(updates) == ["update_1"]
    assert updates["update_1"][0] == "50"


def test_run_sync_is_idempotent_on_second_run(monkeypatch) -> None:
    sector = _sector("1")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector])
    target = sector_sync.build_target_fields(sector)
    existing_by_code = {"1": {"id": "50", "title": "678 - lo que sea", fields.FIELD_SECTOR_UBICACION.uf_crm: target[fields.FIELD_SECTOR_UBICACION.uf_crm]}}
    client = FakeSectorsBitrixClient(existing_by_code=existing_by_code)

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.created == 0
    assert summary.updated == 0
    assert summary.unchanged == 1
    assert summary.errors == []
    assert client.batch_calls == []


def test_run_sync_dry_run_does_not_call_batch_upsert(monkeypatch) -> None:
    sector = _sector("1")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector])
    client = FakeSectorsBitrixClient(existing_by_code={})

    summary = sector_sync.run_sync(client, dry_run=True)

    assert summary.created == 1
    assert summary.updated == 0
    assert client.batch_calls == []


def test_run_sync_isolates_per_item_errors(monkeypatch) -> None:
    sector_ok = _sector("1", sector="Ok")
    sector_bad = _sector("2", sector="Bad")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector_ok, sector_bad])
    batch_result = BatchUpsertResult(
        succeeded_creates={"create_1": "999"},
        failed={"create_2": "ERROR_TITLE_REQUIRED"},
    )
    client = FakeSectorsBitrixClient(existing_by_code={}, batch_result=batch_result)

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.created == 1
    assert len(summary.errors) == 1
    error = summary.errors[0]
    assert error.sector_code == "2"
    assert error.stage == "create"
    assert error.operation == "batch.call"
    assert error.message == "ERROR_TITLE_REQUIRED"


def test_run_sync_aborts_cleanly_when_bitrix_list_fails(monkeypatch) -> None:
    sector = _sector("1")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector])

    class FailingListClient(FakeSectorsBitrixClient):
        def list_sector_items(self):
            self.list_calls += 1
            return None

    client = FailingListClient()

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.created == 0
    assert summary.updated == 0
    assert summary.missing_from_source == []
    assert len(summary.errors) == 1
    assert summary.errors[0].stage == "list"
    assert client.batch_calls == []


def test_run_sync_aborts_cleanly_when_dwh_source_fails(monkeypatch) -> None:
    """`fetch_all_sectores` devuelve `None` (DWH caído, distinto de `[]` = catálogo vacío) —
    `run_sync` debe abortar reportando un error, nunca confundirlo con "todos los sectores de
    Bitrix desaparecieron de la fuente" (bug real: antes de este fix, `None` se trataba como
    lista vacía y `missing_from_source` reportaba falsamente cada sector existente)."""
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: None)
    client = FakeSectorsBitrixClient(existing_by_code={"1": {"id": "50", "title": "x"}})

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.total_source == 0
    assert summary.created == 0
    assert summary.updated == 0
    assert summary.missing_from_source == []
    assert len(summary.errors) == 1
    assert summary.errors[0].stage == "fetch_source"
    assert client.list_calls == 0
    assert client.batch_calls == []


def test_run_sync_reports_duplicate_source_ids_without_syncing_them(monkeypatch) -> None:
    sectores = [_sector("1"), _sector("1", sector="Otro nombre")]
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: sectores)
    client = FakeSectorsBitrixClient(existing_by_code={})

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.skipped_duplicates == ["1"]
    assert summary.created == 0
    assert client.batch_calls == [({}, {})] or client.batch_calls == []


def test_run_sync_limit_truncates_source_before_syncing(monkeypatch) -> None:
    sectores = [_sector(str(i)) for i in range(5)]
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: sectores)
    client = FakeSectorsBitrixClient(existing_by_code={})

    summary = sector_sync.run_sync(client, dry_run=True, limit=3)

    assert summary.total_source == 3
    assert summary.created == 3


def test_run_sync_reports_bitrix_items_missing_from_source_without_touching_them(monkeypatch) -> None:
    sector = _sector("1")
    monkeypatch.setattr(sector_sync, "fetch_all_sectores", lambda: [sector])
    target = sector_sync.build_target_fields(sector)
    existing_by_code = {
        "1": {"id": "50", "title": "678 - lo que sea", fields.FIELD_SECTOR_UBICACION.uf_crm: target[fields.FIELD_SECTOR_UBICACION.uf_crm]},
        "999": {"id": "60", "title": "Sector fantasma", fields.FIELD_SECTOR_UBICACION.uf_crm: "Sector fantasma"},
    }
    client = FakeSectorsBitrixClient(existing_by_code=existing_by_code)

    summary = sector_sync.run_sync(client, dry_run=False)

    assert summary.missing_from_source == ["999"]
    assert client.batch_calls == []
