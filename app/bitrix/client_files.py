"""Mixin de `BitrixClient` (`app/bitrix/client.py`): timeline (comentarios) y Drive (archivos).

Separado de `client.py` por el límite de 500 líneas del repo — ver el
docstring de `BitrixClient` para el resto del reparto (`client_deals.py`,
`client_contacts.py`).
"""
from __future__ import annotations

import logging
from urllib.parse import quote

import requests

from app.bitrix._shared import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_CRM_ENTITY_TYPE_DEAL = 2
_ENTITY_TYPE_DEAL = "deal"


class FilesMixin:
    """Requiere `self.webhook_url` (ver `BitrixClient.__init__`)."""

    def add_comment(self, deal_id: str, comment: str) -> int | None:
        """Agrega un comentario al timeline de un deal.

        Retorna el ID del comentario creado, o None si la llamada falla.
        """
        try:
            response = self.session.post(
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
            response = self.session.post(
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
            response = self.session.post(
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

            upload_response = self.session.post(
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
