"""Lista los VALUE ID de un campo picklist (enumeration) del deal en Bitrix.

Uso:
    uv run python scripts/list_bitrix_picklist_values.py UF_CRM_1773860139420

Sirve para llenar diccionarios como `PROPERTY_TYPE_VALUE_BY_NAME` en
`app/bitrix/fields.py` sin adivinar los IDs — Bitrix asigna un ID numérico
distinto a cada opción de un picklist en cada instalación, así que no se
pueden hardcodear sin consultarlos primero.

Requiere `BITRIX_WEBHOOK_URL` en `.env` (o en el entorno).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from app.bitrix.settings import load_bitrix_settings


def _post(webhook_url: str, method: str, data: dict[str, Any] | None = None) -> Any:
    response = requests.post(f"{webhook_url}{method}.json", json=data or {}, timeout=10)
    response.raise_for_status()
    return response.json().get("result")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    field_id = sys.argv[1]
    webhook_url = load_bitrix_settings().rstrip("/") + "/"

    all_fields = _post(webhook_url, "crm.deal.fields") or {}
    field = all_fields.get(field_id)
    if field is None:
        print(f"El deal no tiene un campo {field_id!r}. Campos UF_CRM_* disponibles:")
        for name in sorted(all_fields):
            if name.startswith("UF_CRM_"):
                print(f"  {name}  ({all_fields[name].get('title')})")
        raise SystemExit(1)

    items = field.get("items")
    if not items:
        print(f"{field_id} no es un picklist (type={field.get('type')}) o no tiene opciones.")
        raise SystemExit(1)

    print(f"Opciones de {field_id} ({field.get('title')}):")
    for item in items:
        print(f"  {item.get('ID')}  {item.get('VALUE')}")


if __name__ == "__main__":
    main()
