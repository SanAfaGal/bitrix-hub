"""Cliente HTTP mínimo para la REST API de Bitrix24 (vía webhook entrante).

Núcleo compartido por todas las integraciones del hub: no se duplica por
integración, cada `flow` o `events` module lo recibe como dependencia.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10

CRM_ENTITY_TYPE_DEAL = 2


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

    def add_comment(self, entity_id: str, entity_type: str, comment: str) -> int | None:
        """Agrega un comentario al timeline de una entidad de Bitrix.

        Retorna el ID del comentario creado, o None si la llamada falla.
        """
        try:
            response = requests.post(
                f"{self.webhook_url}crm.timeline.comment.add.json",
                json={
                    "fields": {
                        "ENTITY_ID": entity_id,
                        "ENTITY_TYPE": entity_type,
                        "COMMENT": comment,
                    }
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            comment_id = payload.get("result") if isinstance(payload, dict) else None
            comment_id = comment_id if isinstance(comment_id, int) and not isinstance(comment_id, bool) else None
            logger.info("Comentario agregado en %s %s (id=%s)", entity_type, entity_id, comment_id)
            return comment_id
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error agregando comentario en %s %s: %s", entity_type, entity_id, exc)
            return None

    def pin_comment(self, comment_id: int, owner_type_id: int, owner_id: str) -> None:
        """Fija un comentario del timeline en el CRM (máx. 3 fijados por entidad). No lanza si falla."""
        try:
            response = requests.post(
                f"{self.webhook_url}crm.timeline.item.pin.json",
                json={"id": comment_id, "ownerTypeId": owner_type_id, "ownerId": owner_id},
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
