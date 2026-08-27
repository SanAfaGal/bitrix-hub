"""Prueba manual: crea un contacto simple (nombre + teléfono) en Bitrix.

Uso:
    uv run python scripts/test_create_contact.py

Crea un contacto con NAME="[Test] CREACION DE CONTACTO" y
PHONE=573167991132 vía `crm.contact.add`, para verificar que Bitrix
lo acepta sin más campos. Contacto queda en Bitrix real — borrar a mano
después de probar.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from app.bitrix.settings import load_bitrix_settings

_TEST_NAME = "[Test] CREACION DE CONTACTO"
_TEST_PHONE = "573167991132"


def main() -> None:
    webhook_url = load_bitrix_settings().rstrip("/") + "/"

    response = requests.post(
        f"{webhook_url}crm.contact.add.json",
        json={
            "fields": {
                "NAME": _TEST_NAME,
                "PHONE": [{"VALUE": _TEST_PHONE, "VALUE_TYPE": "MOBILE"}],
            }
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        print(f"Error de Bitrix: {payload}")
        raise SystemExit(1)

    contact_id = payload.get("result")

    # Bitrix puede borrar el contacto solo (async, control de duplicados
    # interno) justo después de crearlo — el ID de la respuesta no garantiza
    # que siga existiendo.
    verify = requests.post(f"{webhook_url}crm.contact.get.json", json={"id": contact_id}, timeout=10)
    verify_payload = verify.json()
    if "error" in verify_payload:
        print(f"Contacto {contact_id} se creó pero Bitrix lo borró enseguida (duplicado interno).")
        raise SystemExit(1)

    print(f"Contacto creado. ID={contact_id}")


if __name__ == "__main__":
    main()
