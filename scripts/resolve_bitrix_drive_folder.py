"""Busca carpetas de Bitrix Drive por nombre y muestra su ID.

Uso:
    uv run python scripts/resolve_bitrix_drive_folder.py <texto-a-buscar>
    uv run python scripts/resolve_bitrix_drive_folder.py --todos-los-storages <texto-a-buscar>

Por defecto busca solo dentro del Drive del grupo de trabajo "Ventas"
(donde vive la carpeta "Autorizaciones de corretaje" — ver README.md). Con
`--todos-los-storages` recorre además el Drive compartido y el resto de
Drives de grupo accesibles por el webhook (más lento).

Útil para volver a resolver un `BITRIX_DRIVE_FOLDER_ID` si la carpeta
original se borró y se recreó.

Requiere que el webhook (BITRIX_WEBHOOK_URL) tenga el scope "disk"
habilitado y que su usuario sea miembro de los grupos que se quieran
consultar.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from app.bitrix.settings import load_bitrix_settings

# Grupo de trabajo "Ventas" (https://.../workgroups/group/184/disk/path/),
# donde vive hoy la carpeta "Autorizaciones de corretaje".
_VENTAS_WORKGROUP_ID = 184


def _post(webhook_url: str, method: str, data: dict[str, Any] | None = None) -> Any:
    response = requests.post(f"{webhook_url}{method}.json", data=data, timeout=10)
    response.raise_for_status()
    return response.json().get("result")


def _iter_folder_tree(webhook_url: str, folder_id: str, path: str):
    children = _post(webhook_url, "disk.folder.getchildren", {"id": folder_id}) or []
    for child in children:
        child_path = f"{path}/{child.get('NAME')}"
        yield child, child_path
        if child.get("TYPE") == "folder":
            yield from _iter_folder_tree(webhook_url, child.get("ID"), child_path)


def _search_storage(webhook_url: str, storage_id: str, storage_name: str, query: str) -> list[tuple[dict, str]]:
    matches = []
    root_children = _post(webhook_url, "disk.storage.getchildren", {"id": storage_id}) or []
    for child in root_children:
        path = f"/{storage_name}/{child.get('NAME')}"
        candidates = [(child, path)]
        if child.get("TYPE") == "folder":
            candidates += list(_iter_folder_tree(webhook_url, child.get("ID"), path))
        matches += [(item, item_path) for item, item_path in candidates if query in item.get("NAME", "").lower()]
    return matches


def _group_storage(webhook_url: str, workgroup_id: int) -> dict | None:
    storages = _post(
        webhook_url,
        "disk.storage.getlist",
        {"filter[ENTITY_TYPE]": "group", "filter[ENTITY_ID]": workgroup_id},
    )
    return storages[0] if storages else None


def main() -> None:
    args = sys.argv[1:]
    search_all = "--todos-los-storages" in args
    args = [a for a in args if a != "--todos-los-storages"]

    if len(args) != 1:
        print(__doc__)
        raise SystemExit(1)

    query = args[0].lower()
    webhook_url = load_bitrix_settings().rstrip("/") + "/"
    matches_found = False

    if search_all:
        storages = _post(webhook_url, "disk.storage.getlist") or []
    else:
        storage = _group_storage(webhook_url, _VENTAS_WORKGROUP_ID)
        if not storage:
            print(f'No se encontró el Drive del grupo de trabajo {_VENTAS_WORKGROUP_ID} ("Ventas").')
            raise SystemExit(1)
        storages = [storage]

    for storage in storages:
        for item, item_path in _search_storage(webhook_url, storage.get("ID"), storage.get("NAME", ""), query):
            matches_found = True
            print(f"ID={item.get('ID')}  TYPE={item.get('TYPE')}  {item_path}")

    if not matches_found:
        print(f"Sin coincidencias para {args[0]!r}.")


if __name__ == "__main__":
    main()
