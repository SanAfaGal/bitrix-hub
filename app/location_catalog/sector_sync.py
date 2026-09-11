"""Sincroniza el catálogo de sectores de Mobilia DWH hacia el Smart Process
de Bitrix (entityTypeId 1088, ver `app/bitrix/client_sectors.py`).

Mobilia es la única fuente de verdad — Bitrix es un espejo. No vive en
`app/flows/` porque no lo dispara un webhook de Bitrix ni tiene router HTTP
(ver `app/flows/README.md`): lo corre una persona a mano vía
`scripts/sync_mobilia_sectores.py`. Igual mantiene la misma disciplina de una
flow: recibe el `BitrixClient` ya construido como parámetro en vez de
importarlo para construirlo acá.

Reutiliza `app.location_catalog.normalize.build_location_label` — la misma
función que usa el formulario web para mostrar la ubicación — para el campo
Ubicación; no hay un formato nuevo. No se manda TITLE: Bitrix ya tiene una
regla de automatización que arma el nombre del ítem concatenando campos
existentes.

Fuera de alcance a propósito: desactivar en Bitrix los sectores que
desaparecen de la fuente. Se detectan y se reportan en
`SyncSummary.missing_from_source`, pero nunca se tocan.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.bitrix import fields
from app.location_catalog.client import Sector, fetch_all_sectores
from app.location_catalog.normalize import build_location_label

if TYPE_CHECKING:
    from app.bitrix.client import BitrixClient


@dataclass(frozen=True)
class SyncError:
    sector_code: str
    stage: str  # "fetch_source" | "list" | "create" | "update"
    operation: str  # "crm.item.list" | "batch.call"
    message: str


@dataclass(frozen=True)
class SyncSummary:
    total_source: int
    created: int
    updated: int
    unchanged: int
    skipped_duplicates: list[str] = field(default_factory=list)
    missing_from_source: list[str] = field(default_factory=list)
    errors: list[SyncError] = field(default_factory=list)


def dedupe_source(sectores: list[Sector]) -> tuple[list[Sector], list[str]]:
    """Si un `sector_code` aparece más de una vez en la fuente, se excluyen
    TODAS sus apariciones (nunca se elige una silenciosamente) y se reporta
    el código como inconsistencia."""
    counts = Counter(sector.sector_code for sector in sectores)
    duplicate_codes = sorted(code for code, count in counts.items() if count > 1)
    duplicates = set(duplicate_codes)
    deduped = [sector for sector in sectores if sector.sector_code not in duplicates]
    return deduped, duplicate_codes


def build_target_fields(sector: Sector) -> dict[str, str]:
    """Ubicación recibe la etiqueta que ya arma el formulario web para este
    sector. Incluye también la clave de negocio (`FIELD_SECTOR_CODE`) —
    Bitrix la exige como campo requerido al crear, y en un `update`
    reenviarla es un no-op seguro (ya coincide, es justo lo que se usó para
    encontrar el ítem).

    Nunca incluye TITLE: hay una regla de automatización ya configurada en
    Bitrix que arma el nombre del ítem concatenando campos existentes — si
    este sync mandara su propio TITLE, competiría con esa regla."""
    label = build_location_label(sector.sector, sector.zona, sector.ciudad, sector.departamento, sector.pais)
    return {
        fields.FIELD_SECTOR_UBICACION.uf_crm: label,
        fields.FIELD_SECTOR_CODE.uf_crm: sector.sector_code,
    }


def needs_update(existing: dict[str, Any], target_fields: dict[str, str]) -> bool:
    """Compara valores ya normalizados — nunca los crudos del DWH.

    Solo compara Ubicación: TITLE no se manda (lo arma una regla de
    automatización de Bitrix) y por lo tanto no participa en la decisión de
    si hace falta un update."""
    return existing.get(fields.FIELD_SECTOR_UBICACION.uf_crm) != target_fields[fields.FIELD_SECTOR_UBICACION.uf_crm]


def plan_sync(
    sectores: list[Sector], existing_by_code: dict[str, dict[str, Any]]
) -> tuple[list[Sector], list[tuple[str, Sector]], list[str]]:
    """Diff puro, sin I/O: (a_crear, a_actualizar[(item_id, sector)], codigos_sin_cambios)."""
    to_create: list[Sector] = []
    to_update: list[tuple[str, Sector]] = []
    unchanged: list[str] = []

    for sector in sectores:
        existing = existing_by_code.get(sector.sector_code)
        if existing is None:
            to_create.append(sector)
            continue
        target = build_target_fields(sector)
        if needs_update(existing, target):
            to_update.append((str(existing["id"]), sector))
        else:
            unchanged.append(sector.sector_code)

    return to_create, to_update, unchanged


def run_sync(bitrix_client: BitrixClient, dry_run: bool, limit: int | None = None) -> SyncSummary:
    """`limit`: solo para pruebas manuales (ver `scripts/sync_mobilia_sectores.py
    --limit`) — trunca la fuente a los primeros N sectores antes de sincronizar,
    para probar contra Bitrix real sin tocar los ~1.500 de una vez."""
    sectores = fetch_all_sectores()
    if sectores is None:
        return SyncSummary(
            total_source=0,
            created=0,
            updated=0,
            unchanged=0,
            errors=[
                SyncError(
                    sector_code="",
                    stage="fetch_source",
                    operation="fetch_all_sectores",
                    message="No se pudo leer el catálogo de sectores del DWH de Mobilia",
                )
            ],
        )
    if limit is not None:
        sectores = sectores[:limit]
    deduped, duplicate_codes = dedupe_source(sectores)

    existing_by_code = bitrix_client.list_sector_items()
    if existing_by_code is None:
        return SyncSummary(
            total_source=len(sectores),
            created=0,
            updated=0,
            unchanged=0,
            skipped_duplicates=duplicate_codes,
            missing_from_source=[],
            errors=[
                SyncError(
                    sector_code="",
                    stage="list",
                    operation="crm.item.list",
                    message="No se pudo leer el Smart Process de sectores en Bitrix",
                )
            ],
        )

    to_create, to_update, unchanged = plan_sync(deduped, existing_by_code)
    source_codes = {sector.sector_code for sector in deduped}
    missing_from_source = sorted(code for code in existing_by_code if code not in source_codes)

    create_by_key = {f"create_{sector.sector_code}": sector for sector in to_create}
    update_by_key = {f"update_{sector.sector_code}": (item_id, sector) for item_id, sector in to_update}

    created = 0
    updated = 0
    errors: list[SyncError] = []

    if dry_run:
        created = len(to_create)
        updated = len(to_update)
    elif create_by_key or update_by_key:
        creates_payload = {key: build_target_fields(sector) for key, sector in create_by_key.items()}
        updates_payload = {
            key: (item_id, build_target_fields(sector)) for key, (item_id, sector) in update_by_key.items()
        }
        batch_result = bitrix_client.batch_upsert_sector_items(creates_payload, updates_payload)

        for key, sector in create_by_key.items():
            if key in batch_result.failed:
                errors.append(SyncError(sector.sector_code, "create", "batch.call", batch_result.failed[key]))
            else:
                created += 1
        for key, (_item_id, sector) in update_by_key.items():
            if key in batch_result.failed:
                errors.append(SyncError(sector.sector_code, "update", "batch.call", batch_result.failed[key]))
            else:
                updated += 1

    return SyncSummary(
        total_source=len(sectores),
        created=created,
        updated=updated,
        unchanged=len(unchanged),
        skipped_duplicates=duplicate_codes,
        missing_from_source=missing_from_source,
        errors=errors,
    )
