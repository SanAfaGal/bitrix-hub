"""Mixin de `BitrixClient` (`app/bitrix/client.py`): Smart Process "Sectores" (entityTypeId 1088).

Separado de `client.py` por el límite de 500 líneas del repo (ver el
docstring de `BitrixClient`). A diferencia de `client_deals.py`/
`client_contacts.py`, usa la API de Smart Process (`crm.item.*`/`batch.json`)
en vez de la clásica (`crm.deal.*`) — no hay antecedente de esto en el repo,
así que los nombres/shapes de parámetros se verificaron contra la
documentación pública de Bitrix24 al momento de escribir esto, no contra un
portal real. `useOriginalUfNames="Y"` se manda siempre para poder direccionar
los campos como `UF_CRM_20_...` (nombre técnico real) en vez del alias
camelCase (`ufCrm20_...`) que la API devuelve por defecto.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import requests

from app.bitrix import fields
from app.bitrix._shared import REQUEST_TIMEOUT, error_detail

logger = logging.getLogger(__name__)

_LIST_PAGE_SIZE = 50
_BATCH_CHUNK_SIZE = 50
_MAX_LIST_PAGES = 200  # ~10.000 ítems — tope de seguridad ante un "next" que no converge


@dataclass(frozen=True)
class BatchUpsertResult:
    succeeded_creates: dict[str, str] = field(default_factory=dict)
    succeeded_updates: set[str] = field(default_factory=set)
    failed: dict[str, str] = field(default_factory=dict)


def _flatten_params(params: dict[str, Any], parent_key: str = "") -> list[tuple[str, Any]]:
    """Bitrix batch espera cada `cmd` como query string; los dict anidados
    (ej. `fields={...}`) van con notación `fields[CAMPO]=valor`."""
    items: list[tuple[str, Any]] = []
    for key, value in params.items():
        full_key = f"{parent_key}[{key}]" if parent_key else key
        if isinstance(value, dict):
            items.extend(_flatten_params(value, full_key))
        else:
            items.append((full_key, value))
    return items


def _build_batch_cmd(method: str, params: dict[str, Any]) -> str:
    return f"{method}?{urlencode(_flatten_params(params))}"


def _extract_items(payload: Any) -> list[dict[str, Any]] | None:
    """Tolera tanto `result.items` (documentado) como `result` como lista
    plana — no hay forma de confirmar cuál devuelve este portal sin probarlo."""
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if isinstance(result, dict):
        items = result.get("items")
        return items if isinstance(items, list) else None
    if isinstance(result, list):
        return result
    return None


class SectorsMixin:
    """Requiere `self.webhook_url` (ver `BitrixClient.__init__`)."""

    def list_sector_items(self) -> dict[str, dict[str, Any]] | None:
        """Trae todos los ítems del Smart Process de sectores, indexados por
        `FIELD_SECTOR_CODE`. `None` si la primera página falla (Bitrix
        ilegible, hay que abortar); `{}` si Bitrix no tiene ítems todavía
        (caso legítimo, no un error)."""
        items_by_code: dict[str, dict[str, Any]] = {}
        start: int | None = None
        for _ in range(_MAX_LIST_PAGES):
            request_body: dict[str, Any] = {
                "entityTypeId": fields.SECTOR_ENTITY_TYPE_ID,
                # `select` con nombres de campo explícitos (ej. "id", "title",
                # sin importar mayúsculas) hace que este portal los omita del
                # resultado por completo — confirmado contra Bitrix real, no
                # documentado. "*" (estándar) + "UF_*" (custom) sí funciona.
                "select": ["*", "UF_*"],
                "useOriginalUfNames": "Y",
            }
            if start is not None:
                request_body["start"] = start
            try:
                # POST con `select` como array JSON — un GET con `select`
                # repetido en la query string (`select=a&select=b`) lo
                # rechaza este portal: "Should be value of type array"
                # (confirmado contra Bitrix real, no es solo teórico).
                response = self.session.post(
                    f"{self.webhook_url}crm.item.list.json",
                    json=request_body,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.exceptions.RequestException, ValueError) as exc:
                logger.error("Error listando ítems del Smart Process de sectores: %s%s", exc, error_detail(exc))
                return None if start is None else items_by_code

            items = _extract_items(payload)
            if items is None:
                logger.error("Respuesta inesperada de crm.item.list para sectores: %s", payload)
                return None if start is None else items_by_code

            for item in items:
                code = item.get(fields.FIELD_SECTOR_CODE.uf_crm)
                if not code:
                    logger.warning(
                        "Ítem de Smart Process de sectores sin %s, se omite: %s", fields.FIELD_SECTOR_CODE.uf_crm, item
                    )
                    continue
                items_by_code[str(code)] = item

            next_start = payload.get("next") if isinstance(payload, dict) else None
            if next_start is None:
                break
            start = next_start
        return items_by_code

    def get_sector_item(self, item_id: str) -> dict[str, Any]:
        """Obtiene un ítem del Smart Process de Sectores por su id de Bitrix. Retorna {} si falla o no existe.

        Usado para mostrar la ubicación legible de un deal (ver
        `DealsMixin.get_property_listing`) — el deal solo guarda el vínculo
        (`FIELD_DEAL_UBICACION_SECTOR`), no una copia del texto.
        """
        try:
            response = self.session.post(
                f"{self.webhook_url}crm.item.get.json",
                json={"entityTypeId": fields.SECTOR_ENTITY_TYPE_ID, "id": item_id, "useOriginalUfNames": "Y"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            item = payload.get("result", {}).get("item") if isinstance(payload, dict) else None
            return item if isinstance(item, dict) else {}
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error consultando ítem %s del Smart Process de sectores: %s%s", item_id, exc, error_detail(exc))
            return {}

    def find_sector_item_id_by_code(self, sector_code: str) -> str | None:
        """Busca el id de Bitrix de un ítem del Smart Process de Sectores por
        `sector_code` de Mobilia — un solo ítem vía `filter`, no trae los
        ~1.500 ítems como `list_sector_items()`. Usado para vincular el campo
        "[Ventas] Ubicación" (`FIELD_DEAL_UBICACION_SECTOR`) del deal.
        """
        try:
            response = self.session.post(
                f"{self.webhook_url}crm.item.list.json",
                json={
                    "entityTypeId": fields.SECTOR_ENTITY_TYPE_ID,
                    "filter": {fields.FIELD_SECTOR_CODE.uf_crm: sector_code},
                    "select": ["*", "UF_*"],
                    "useOriginalUfNames": "Y",
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error buscando ítem de sector %s en Bitrix: %s%s", sector_code, exc, error_detail(exc))
            return None

        items = _extract_items(payload)
        if not items:
            return None
        item_id = items[0].get("id")
        return str(item_id) if item_id else None

    def create_sector_item(self, item_fields: dict[str, Any]) -> str | None:
        """Crea un ítem del Smart Process de sectores. Retorna el nuevo id o None si falla."""
        try:
            response = self.session.post(
                f"{self.webhook_url}crm.item.add.json",
                json={
                    "entityTypeId": fields.SECTOR_ENTITY_TYPE_ID,
                    "fields": item_fields,
                    "useOriginalUfNames": "Y",
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            item = payload.get("result", {}).get("item") if isinstance(payload, dict) else None
            item_id = item.get("id") if isinstance(item, dict) else None
            return str(item_id) if item_id else None
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error creando ítem del Smart Process de sectores: %s%s", exc, error_detail(exc))
            return None

    def update_sector_item(self, item_id: str, item_fields: dict[str, Any]) -> bool:
        """Actualiza un ítem del Smart Process de sectores. Retorna False si falla."""
        try:
            response = self.session.post(
                f"{self.webhook_url}crm.item.update.json",
                json={
                    "entityTypeId": fields.SECTOR_ENTITY_TYPE_ID,
                    "id": item_id,
                    "fields": item_fields,
                    "useOriginalUfNames": "Y",
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            return isinstance(payload, dict) and "result" in payload
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error actualizando ítem %s del Smart Process de sectores: %s%s", item_id, exc, error_detail(exc))
            return False

    def batch_upsert_sector_items(
        self,
        creates: dict[str, dict[str, Any]],
        updates: dict[str, tuple[str, dict[str, Any]]],
    ) -> BatchUpsertResult:
        """Crea/actualiza en lote vía `batch.json` (`halt=0`: un cmd fallido no tumba el resto).

        `creates`/`updates` vienen indexados por una cmd key opaca que elige
        el llamador (ver `app.location_catalog.sector_sync.run_sync`) — así el
        resultado se puede mapear de vuelta al sector original sin una
        segunda búsqueda.
        """
        cmds: dict[str, str] = {}
        for key, item_fields in creates.items():
            cmds[key] = _build_batch_cmd(
                "crm.item.add",
                {"entityTypeId": fields.SECTOR_ENTITY_TYPE_ID, "fields": item_fields, "useOriginalUfNames": "Y"},
            )
        for key, (item_id, item_fields) in updates.items():
            cmds[key] = _build_batch_cmd(
                "crm.item.update",
                {
                    "entityTypeId": fields.SECTOR_ENTITY_TYPE_ID,
                    "id": item_id,
                    "fields": item_fields,
                    "useOriginalUfNames": "Y",
                },
            )

        result = BatchUpsertResult()
        if not cmds:
            return result

        create_keys = set(creates)
        cmd_keys = list(cmds)
        for start in range(0, len(cmd_keys), _BATCH_CHUNK_SIZE):
            chunk_keys = cmd_keys[start : start + _BATCH_CHUNK_SIZE]
            chunk_cmds = {key: cmds[key] for key in chunk_keys}
            try:
                response = self.session.post(
                    f"{self.webhook_url}batch.json",
                    json={"halt": 0, "cmd": chunk_cmds},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
                batch_result = payload.get("result", {}) if isinstance(payload, dict) else {}
                successes = batch_result.get("result", {}) if isinstance(batch_result, dict) else {}
                batch_errors = batch_result.get("result_error", {}) if isinstance(batch_result, dict) else {}
            except (requests.exceptions.RequestException, ValueError) as exc:
                message = f"Error de red/HTTP en batch.call: {exc}{error_detail(exc)}"
                logger.error(message)
                for key in chunk_keys:
                    result.failed[key] = message
                continue

            for key in chunk_keys:
                if key in batch_errors:
                    result.failed[key] = str(batch_errors[key])
                    continue
                if key not in successes:
                    result.failed[key] = "Bitrix no devolvió resultado para este cmd en el batch"
                    continue
                if key in create_keys:
                    item = successes[key].get("item") if isinstance(successes[key], dict) else None
                    item_id = item.get("id") if isinstance(item, dict) else None
                    if item_id:
                        result.succeeded_creates[key] = str(item_id)
                    else:
                        result.failed[key] = "Bitrix no devolvió id del ítem creado"
                else:
                    result.succeeded_updates.add(key)

        return result
