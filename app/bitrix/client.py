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
from urllib.parse import quote

import requests

from app.bitrix import fields
from app.crm.protocol import AuthorizationStatus

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10

_CRM_ENTITY_TYPE_DEAL = 2
_ENTITY_TYPE_DEAL = "deal"

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
        contact_id = deal.get(fields.FIELD_CONTACT_ID)
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
            value_type_raw = entry.get("VALUE_TYPE")
            value_type = value_type_raw if isinstance(value_type_raw, str) else ""
            if isinstance(value, str) and value.strip():
                by_type.setdefault(value_type, value)

        for preferred_type in _PREFERRED_PHONE_TYPES:
            if preferred_type in by_type:
                return by_type[preferred_type]

        return next(iter(by_type.values()), None)

    def get_matricula(self, deal: dict[str, Any]) -> str | None:
        """Extrae la matrícula del inmueble de un deal (campo UF_CRM_1773860489786)."""
        matricula = deal.get(fields.FIELD_MATRICULA)
        return str(matricula) if matricula else None

    def set_duplicado_status(self, deal_id: str, has_duplicate: bool) -> None:
        """Marca el campo Duplicado/Sin duplicado (UF_CRM_1773861337167) del deal."""
        value = fields.VALUE_DUPLICADO if has_duplicate else fields.VALUE_SIN_DUPLICADO
        self.update_deal(deal_id, {fields.FIELD_DUPLICADO: value})

    def get_authorization_status(self, deal: dict[str, Any]) -> AuthorizationStatus | None:
        """Extrae el estado de firma de la Autorización de Corretaje (UF_CRM_1773864282733)."""
        value = deal.get(fields.FIELD_AUTHORIZATION_STATUS)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return fields.AUTHORIZATION_STATUS_BY_VALUE.get(value)

    def set_authorization_status(self, deal_id: str, status: AuthorizationStatus) -> None:
        """Marca el estado de firma de la Autorización de Corretaje (UF_CRM_1773864282733) del deal."""
        self.update_deal(deal_id, {fields.FIELD_AUTHORIZATION_STATUS: fields.AUTHORIZATION_VALUE_BY_STATUS[status]})

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

    def upload_file(self, folder_id: str, filename: str, content: bytes) -> str | None:
        """Sube un archivo a una carpeta de Bitrix Drive (flujo Disk en dos pasos).

        Retorna el link de visualización dentro del portal (DETAIL_URL), o
        None si falla.
        """
        try:
            response = requests.post(
                f"{self.webhook_url}disk.folder.uploadfile.json",
                # generateUniqueName evita el error DISK_OBJ_22000 si ya existe un
                # archivo con el mismo nombre (Bitrix le agrega un sufijo " (1)").
                data={"id": folder_id, "generateUniqueName": "Y"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            upload_url = (payload.get("result") or {}).get("uploadUrl") if isinstance(payload, dict) else None
            if not upload_url:
                logger.error("Bitrix no devolvió uploadUrl para la carpeta %s", folder_id)
                return None

            upload_response = requests.post(
                upload_url,
                files={"file": (filename, content)},
                timeout=REQUEST_TIMEOUT,
            )
            upload_response.raise_for_status()
            upload_payload = upload_response.json()
            file_info = upload_payload.get("result") if isinstance(upload_payload, dict) else None
            detail_url = file_info.get("DETAIL_URL") if isinstance(file_info, dict) else None
            if not isinstance(detail_url, str) or not detail_url:
                logger.error("Bitrix no devolvió DETAIL_URL al subir %s", filename)
                return None

            logger.info("Archivo %s subido a Bitrix Drive (carpeta %s)", filename, folder_id)
            # DETAIL_URL trae la ruta con espacios/acentos sin codificar (ej. nombres de
            # carpeta como "Autorizaciones de corretaje"); si se pega tal cual en texto
            # plano (comentario del timeline), Bitrix corta el link en el primer espacio.
            return quote(detail_url, safe=":/?&=%")
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error subiendo archivo %s a Bitrix Drive: %s", filename, exc)
            return None

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
