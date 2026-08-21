"""Cliente HTTP mínimo para la REST API de Bitrix24 (vía webhook entrante).

Implementa `app.crm.protocol.CrmClient`: expone tanto las llamadas HTTP
crudas (`get_deal`, `get_contact`, `update_deal`) como los métodos de
negocio (`get_matricula`, `set_duplicado_status`, etc.) que traducen esas
llamadas a los campos custom (`UF_CRM_*`) y convenciones específicas de
esta instancia de Bitrix. Todo ese conocimiento vive acá — el resto del
hub solo conoce `CrmClient`.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10

_CRM_ENTITY_TYPE_DEAL = 2
_ENTITY_TYPE_DEAL = "deal"

_FIELD_CONTACT_ID = "CONTACT_ID"
_FIELD_MATRICULA = "UF_CRM_1773860489786"
_FIELD_DUPLICADO = "UF_CRM_1773861337167"
_VALUE_SIN_DUPLICADO = 89296
_VALUE_DUPLICADO = 89298

# Tipos de teléfono de Bitrix, en orden de preferencia para notificar por WhatsApp.
_PREFERRED_PHONE_TYPES = ("MOBILE", "WORK", "HOME", "OTHER")


class BitrixClient:
    """Encapsula las llamadas a la REST API de Bitrix."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url.rstrip("/") + "/"

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        """Obtiene los campos de un deal de Bitrix. Retorna {} si la llamada falla."""
        try:
            response = requests.get(
                f"{self.webhook_url}crm.deal.get.json",
                params={"id": deal_id},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return {}
            result = payload.get("result")
            return result if isinstance(result, dict) else {}
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error consultando deal %s en Bitrix: %s", deal_id, exc)
            return {}

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Obtiene los campos de un contacto de Bitrix. Retorna {} si la llamada falla."""
        try:
            response = requests.get(
                f"{self.webhook_url}crm.contact.get.json",
                params={"id": contact_id},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return {}
            result = payload.get("result")
            return result if isinstance(result, dict) else {}
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error consultando contacto %s en Bitrix: %s", contact_id, exc)
            return {}

    def get_deal_contact_id(self, deal: dict[str, Any]) -> str | None:
        """Extrae el ID del contacto vinculado a un deal (campo CONTACT_ID de Bitrix)."""
        contact_id = deal.get(_FIELD_CONTACT_ID)
        return str(contact_id) if contact_id else None

    def get_contact_phone(self, contact: dict[str, Any]) -> str | None:
        """Extrae el mejor teléfono disponible del campo PHONE de un contacto de Bitrix.

        Bitrix guarda el teléfono como una lista de entradas
        `{"VALUE": "...", "VALUE_TYPE": "..."}`, nunca un string simple.
        Prefiere MOBILE si hay varios números; si no, toma el primero que haya.
        """
        phones = contact.get("PHONE")
        if not isinstance(phones, list) or not phones:
            return None

        by_type: dict[str, str] = {}
        for entry in phones:
            if not isinstance(entry, dict):
                continue
            value = entry.get("VALUE")
            value_type = entry.get("VALUE_TYPE")
            if isinstance(value, str) and value.strip():
                by_type.setdefault(value_type, value)

        for preferred_type in _PREFERRED_PHONE_TYPES:
            if preferred_type in by_type:
                return by_type[preferred_type]

        return next(iter(by_type.values()), None)

    def get_matricula(self, deal: dict[str, Any]) -> str | None:
        """Extrae la matrícula del inmueble de un deal (campo UF_CRM_1773860489786)."""
        matricula = deal.get(_FIELD_MATRICULA)
        return str(matricula) if matricula else None

    def set_duplicado_status(self, deal_id: str, has_duplicate: bool) -> None:
        """Marca el campo Duplicado/Sin duplicado (UF_CRM_1773861337167) del deal."""
        value = _VALUE_DUPLICADO if has_duplicate else _VALUE_SIN_DUPLICADO
        self.update_deal(deal_id, {_FIELD_DUPLICADO: value})

    def add_comment(self, deal_id: str, comment: str) -> int | None:
        """Agrega un comentario al timeline de un deal.

        Retorna el ID del comentario creado, o None si la llamada falla.
        """
        try:
            response = requests.post(
                f"{self.webhook_url}crm.timeline.comment.add.json",
                json={
                    "fields": {
                        "ENTITY_ID": deal_id,
                        "ENTITY_TYPE": _ENTITY_TYPE_DEAL,
                        "COMMENT": comment,
                    }
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            comment_id = payload.get("result") if isinstance(payload, dict) else None
            comment_id = comment_id if isinstance(comment_id, int) and not isinstance(comment_id, bool) else None
            logger.info("Comentario agregado en deal %s (id=%s)", deal_id, comment_id)
            return comment_id
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error agregando comentario en deal %s: %s", deal_id, exc)
            return None

    def pin_comment(self, comment_id: int, deal_id: str) -> None:
        """Fija un comentario del timeline en el deal (máx. 3 fijados por entidad). No lanza si falla."""
        try:
            response = requests.post(
                f"{self.webhook_url}crm.timeline.item.pin.json",
                json={"id": comment_id, "ownerTypeId": _CRM_ENTITY_TYPE_DEAL, "ownerId": deal_id},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info("Comentario %s fijado en el timeline", comment_id)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error fijando comentario %s: %s", comment_id, exc)

    def update_deal(self, deal_id: str, fields: dict[str, Any]) -> None:
        """Actualiza campos de un deal de Bitrix. No lanza si falla."""
        try:
            response = requests.post(
                f"{self.webhook_url}crm.deal.update.json",
                json={"id": deal_id, "fields": fields},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info("Deal %s actualizado: %s", deal_id, fields)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error actualizando deal %s: %s", deal_id, exc)
