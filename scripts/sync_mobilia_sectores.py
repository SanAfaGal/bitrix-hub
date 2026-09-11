"""Sincroniza el catálogo de sectores de Mobilia DWH hacia el Smart Process
de Bitrix (entityTypeId 1088). Mobilia es la fuente de verdad; Bitrix queda
como espejo — ver `app/location_catalog/sector_sync.py` para el detalle del
algoritmo y `docs/sync-mobilia-sectores.md` para el diseño completo.

Uso:
    uv run python scripts/sync_mobilia_sectores.py                    # sincroniza de verdad
    uv run python scripts/sync_mobilia_sectores.py --dry-run          # solo reporta, no escribe en Bitrix
    uv run python scripts/sync_mobilia_sectores.py --limit 3          # solo los primeros N sectores de la fuente
    uv run python scripts/sync_mobilia_sectores.py --dry-run --limit 3

Requiere `BITRIX_WEBHOOK_URL` y `MOBILIA_DWH_*` en `.env` (o en el entorno).
Termina con código de salida 1 si hubo algún error, para que un cron/scheduler
futuro lo pueda detectar.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bitrix.client import BitrixClient
from app.bitrix.settings import load_bitrix_settings
from app.location_catalog.sector_sync import run_sync


def _print_summary(summary) -> None:
    print("Sincronización finalizada")
    print()
    print(f"Total origen:       {summary.total_source}")
    print(f"Creados:            {summary.created}")
    print(f"Actualizados:       {summary.updated}")
    print(f"Sin cambios:        {summary.unchanged}")
    print(f"Omitidos (dup.):    {len(summary.skipped_duplicates)}")
    print(f"Errores:            {len(summary.errors)}")

    if summary.skipped_duplicates:
        print()
        print("ID Sector duplicados en la fuente (omitidos, no sincronizados):")
        for code in summary.skipped_duplicates:
            print(f"  {code}")

    if summary.missing_from_source:
        print()
        print("En Bitrix pero ya no están en la fuente (no se tocan):")
        for code in summary.missing_from_source:
            print(f"  {code}")

    if summary.errors:
        print()
        print("Errores:")
        for error in summary.errors:
            print(f"  sector_code={error.sector_code} etapa={error.stage} operacion={error.operation}: {error.message}")


def _parse_limit(args: list[str]) -> int | None:
    if "--limit" not in args:
        return None
    value = args[args.index("--limit") + 1]
    return int(value)


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    limit = _parse_limit(args)

    client = BitrixClient(load_bitrix_settings())
    summary = run_sync(client, dry_run=dry_run, limit=limit)

    if dry_run:
        print("(dry-run: no se realizó ningún cambio en Bitrix)")
        print()
    _print_summary(summary)

    if summary.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
