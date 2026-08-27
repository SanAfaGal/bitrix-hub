"""Prueba manual: crea una negociación (deal) de consignación para un contacto.

Uso:
    uv run python scripts/test_create_deal.py

Usa el flujo real (`find_or_create_property_seller_contact` +
`find_or_create_property_seller_deal`) con nombre/teléfono de prueba, sobre
el embudo de consignación (CATEGORY_ID=34, `app/bitrix/fields.py`). El deal
se crea sin STAGE_ID explícito — Bitrix lo deja en la primera etapa del
embudo ("Nuevo"). Si ya existe un deal abierto para el contacto, lo
devuelve en vez de crear otro. Todo queda en Bitrix real — borrar a mano
después de probar.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bitrix.client import BitrixClient
from app.bitrix.settings import load_bitrix_settings

_TEST_NAME = "[Test] CREACION DE CONTACTO"
_TEST_PHONE = "573167991132"


def main() -> None:
    client = BitrixClient(load_bitrix_settings())

    contact_id = client.find_or_create_property_seller_contact(_TEST_PHONE, display_name=_TEST_NAME)
    if contact_id is None:
        print("No se pudo obtener/crear el contacto — ver logs arriba.")
        raise SystemExit(1)
    print(f"Contacto: ID={contact_id}")

    deal_id = client.find_or_create_property_seller_deal(contact_id)
    if deal_id is None:
        print("No se pudo obtener/crear el deal — ver logs arriba.")
        raise SystemExit(1)
    print(f"Deal: ID={deal_id}")


if __name__ == "__main__":
    main()
