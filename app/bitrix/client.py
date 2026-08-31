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
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from app.bitrix import fields
from app.crm.protocol import AuthorizationStatus, PropertyListing

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10

_CRM_ENTITY_TYPE_DEAL = 2
_ENTITY_TYPE_DEAL = "deal"

# Tipos de teléfono de Bitrix, en orden de preferencia para notificar por WhatsApp.
_PREFERRED_PHONE_TYPES = ("MOBILE", "WORK", "HOME", "OTHER")


class _BitrixLookupError(Exception):
    """Interna: una búsqueda (no una creación) falló por red/HTTP. Nunca sale de este módulo."""


def _error_detail(exc: Exception) -> str:
    """Extrae el cuerpo de la respuesta de un HTTPError, si lo hay — Bitrix manda el motivo real ahí.

    `raise_for_status()` lanza antes de poder leer el body, así que sin esto
    un 400 de Bitrix se loguea sin decir *qué* campo rechazó.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        return f" | respuesta Bitrix: {response.json()}"
    except ValueError:
        return f" | respuesta Bitrix: {response.text}"


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

    def deal_exists(self, deal_id: str) -> bool:
        """Confirma si un deal existe en Bitrix (a diferencia de get_deal, distingue 'no existe' de una falla de red/timeout).

        Ante un 400 con `error_description` "Not found" (lo que devuelve
        Bitrix para un ID borrado o inválido), retorna False. Ante cualquier
        otro error, asume que existe — no hay forma de confirmarlo, y
        asumir que no existe llevaría a recrear el deal de más por una
        falla transitoria.
        """
        try:
            response = requests.get(
                f"{self.webhook_url}crm.deal.get.json",
                params={"id": deal_id},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError as exc:
            response = getattr(exc, "response", None)
            if response is not None and response.status_code == 400:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                if isinstance(body, dict) and body.get("error_description") == "Not found":
                    return False
            return True
        except requests.exceptions.RequestException:
            return True

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

    def get_bot_active(self, deal_id: str) -> bool:
        """Lee el checkbox de bot activo/pausado (`fields.FIELD_BOT_ACTIVE`) del deal.

        Vacío/None (deal sin el campo, o creado antes de que existiera) se
        interpreta como activo — no pausa deals viejos por omisión.
        """
        deal = self.get_deal(deal_id)
        value = deal.get(fields.FIELD_BOT_ACTIVE)
        if value in (None, ""):
            return True
        return str(value) not in ("0", "N", "false", "False")

    def set_bot_active(self, deal_id: str, active: bool) -> None:
        """Marca el checkbox de bot activo/pausado (`fields.FIELD_BOT_ACTIVE`) del deal."""
        self.update_deal(deal_id, {fields.FIELD_BOT_ACTIVE: 1 if active else 0})

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

    def find_or_create_property_seller_contact(
        self, phone: str | None, username: str | None = None, display_name: str | None = None
    ) -> str | None:
        """Busca un contacto por teléfono (o por `username` si no hay teléfono); si no existe, lo crea.

        `username` cubre el caso de un remitente de WhatsApp con el número
        oculto (chat `@lid`, ver `app.waha.phone.lid_from_chat_id`) — se
        guarda en `fields.FIELD_USERNAME`, no reemplaza al teléfono. El
        nombre real del contacto lo completa el asesor después si no se
        pasa `display_name` — acá solo importa no perder el hilo con un
        cliente que ya escribió antes.

        **Solo crea un contacto nuevo si hay `phone`** — esta instancia de
        Bitrix tiene "Teléfono" como campo obligatorio del contacto
        (`crm.contact.add` rechaza con 400 si no viene). Sin teléfono, si
        `username` no matchea ningún contacto existente, retorna `None` —
        no hay forma correcta de crear el contacto todavía.

        Si el teléfono ya tiene un Lead sin convertir (nunca pasó por
        contacto), no se crea un contacto "desde cero" — el control de
        duplicados nativo de Bitrix lo detecta como duplicado del Lead y lo
        borra automáticamente apenas se crea (probado: ni vincularlo al
        lead después evita el borrado). En ese caso no se crea nada —
        retorna `None`, mismo comportamiento que "no se pudo crear", para
        que un asesor lo enganche a mano.
        """
        if not phone and not username:
            logger.error("find_or_create_property_seller_contact llamado sin teléfono ni username")
            return None

        lead_id: str | None = None
        try:
            if phone:
                contact_id, lead_id = self._find_duplicates_by_phone(phone)
                if contact_id is not None:
                    return contact_id

            if username:
                contact_id = self._find_contact_by_username(username)
                if contact_id is not None:
                    return contact_id
        except _BitrixLookupError:
            return None

        if not phone:
            logger.info(
                "Sin teléfono (username=%s) — Bitrix exige teléfono para crear contacto, se omite", username
            )
            return None

        if lead_id is not None:
            logger.warning(
                "Teléfono %s ya tiene un lead sin convertir (id=%s) — no se crea contacto, requiere enganche manual",
                phone,
                lead_id,
            )
            return None

        return self._create_contact(phone, username, display_name)

    def _find_duplicates_by_phone(self, phone: str) -> tuple[str | None, str | None]:
        """Busca contacto y lead existentes para `phone` en una sola llamada a Bitrix.

        Retorna `(contact_id, lead_id)` — cualquiera puede ser `None`. El
        lead importa aunque haya contacto: `find_or_create_property_seller_contact`
        solo lo usa cuando no hay contacto (ver ahí). Lanza `_BitrixLookupError`
        si falla la llamada.

        `crm.duplicate.findbycomm` compara el valor tal cual está guardado —
        no normaliza. Los contactos nuevos se guardan con `+` delante
        (`_create_contact`) y hay contactos viejos guardados en formato
        local (sin `57`) o sin `+`, así que se manda el teléfono completo,
        con `+` y la variante local (últimos 10 dígitos) cuando aplica; si
        no, un contacto con alguno de esos formatos no aparece acá, Bitrix
        lo crea igual y su propio control de duplicados (que sí normaliza)
        lo borra después.
        """
        values = [phone, f"+{phone}"]
        if phone.startswith("57") and len(phone) > 10:
            values.append(phone[-10:])

        try:
            response = requests.post(
                f"{self.webhook_url}crm.duplicate.findbycomm.json",
                json={"type": "PHONE", "values": values},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") if isinstance(payload, dict) else None
            contact_ids = result.get("CONTACT") if isinstance(result, dict) else None
            lead_ids = result.get("LEAD") if isinstance(result, dict) else None

            contact_id = None
            if isinstance(contact_ids, list) and contact_ids:
                contact_id = str(contact_ids[0])
                logger.info("Contacto encontrado en Bitrix para %s (id=%s)", phone, contact_id)

            lead_id = None
            if isinstance(lead_ids, list) and lead_ids:
                lead_id = str(lead_ids[0])
                logger.info("Lead sin convertir encontrado en Bitrix para %s (id=%s)", phone, lead_id)

            return contact_id, lead_id
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error buscando duplicados por teléfono %s en Bitrix: %s%s", phone, exc, _error_detail(exc))
            raise _BitrixLookupError from exc

    def _find_contact_by_username(self, username: str) -> str | None:
        """Retorna el contact_id si hay match, o None si no hay ninguno. Lanza `_BitrixLookupError` si falla la llamada."""
        try:
            response = requests.post(
                f"{self.webhook_url}crm.contact.list.json",
                json={"filter": {fields.FIELD_USERNAME: username}, "select": ["ID"]},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, list) and result:
                contact_id = result[0].get("ID")
                if contact_id:
                    logger.info("Contacto encontrado en Bitrix para username %s (id=%s)", username, contact_id)
                    return str(contact_id)
            return None
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error(
                "Error buscando contacto por username %s en Bitrix: %s%s", username, exc, _error_detail(exc)
            )
            raise _BitrixLookupError from exc

    def _create_contact(self, phone: str | None, username: str | None, display_name: str | None) -> str | None:
        contact_fields: dict[str, Any] = {"NAME": display_name or "Contacto WhatsApp"}
        if phone:
            phone_value = phone if phone.startswith("+") else f"+{phone}"
            contact_fields["PHONE"] = [{"VALUE": phone_value, "VALUE_TYPE": "MOBILE"}]
        if username:
            contact_fields[fields.FIELD_USERNAME] = username

        try:
            response = requests.post(
                f"{self.webhook_url}crm.contact.add.json",
                json={"fields": contact_fields},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            contact_id = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(contact_id, int) or isinstance(contact_id, bool):
                return None

            # Bitrix devuelve el ID como éxito aunque después borre el contacto
            # solo (de forma asíncrona) por control de duplicados propio, ver
            # docstring de find_or_create_property_seller_contact. Confirmar
            # que sigue vivo antes de darlo por creado.
            if not self.get_contact(str(contact_id)):
                logger.warning(
                    "Bitrix creó el contacto %s para %s pero lo borró enseguida (duplicado interno)",
                    contact_id,
                    phone or username,
                )
                return None

            logger.info("Contacto creado en Bitrix para %s (id=%s)", phone or username, contact_id)
            return str(contact_id)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error(
                "Error creando contacto para %s en Bitrix: %s%s", phone or username, exc, _error_detail(exc)
            )
            return None

    def find_or_create_property_seller_deal(self, contact_id: str) -> str | None:
        """Busca un deal de consignación abierto para el contacto; si no existe, lo crea."""
        try:
            response = requests.post(
                f"{self.webhook_url}crm.deal.list.json",
                json={
                    "filter": {"CONTACT_ID": contact_id, "CATEGORY_ID": fields.CONSIGNACION_CATEGORY_ID},
                    "select": ["ID"],
                    "order": {"ID": "DESC"},
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, list) and result:
                deal_id = result[0].get("ID")
                if deal_id:
                    logger.info(
                        "Deal de consignación encontrado en Bitrix para contacto %s (id=%s)", contact_id, deal_id
                    )
                    return str(deal_id)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error(
                "Error buscando deal de consignación para contacto %s en Bitrix: %s%s",
                contact_id,
                exc,
                _error_detail(exc),
            )
            return None

        try:
            response = requests.post(
                f"{self.webhook_url}crm.deal.add.json",
                json={
                    "fields": {
                        "CONTACT_ID": contact_id,
                        "CATEGORY_ID": fields.CONSIGNACION_CATEGORY_ID,
                        "TITLE": f"Consignación WhatsApp - contacto {contact_id}",
                        fields.FIELD_FIRST_CONTACT: datetime.now(timezone.utc).isoformat(),
                        fields.FIELD_BOT_ACTIVE: 1,
                    }
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            deal_id = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(deal_id, int) or isinstance(deal_id, bool):
                return None
            logger.info("Deal de consignación creado en Bitrix para contacto %s (id=%s)", contact_id, deal_id)
            return str(deal_id)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error(
                "Error creando deal de consignación para contacto %s en Bitrix: %s%s",
                contact_id,
                exc,
                _error_detail(exc),
            )
            return None

    def get_property_listing(self, deal_id: str) -> PropertyListing:
        """Lee los datos del inmueble ya guardados en el deal (lo que falta queda en None)."""
        deal = self.get_deal(deal_id)
        return PropertyListing(
            property_type=self._property_type_name(deal.get(fields.FIELD_PROPERTY_TYPE)),
            address=self._as_text(deal.get(fields.FIELD_ADDRESS)),
            sector_zone_city=self._as_text(deal.get(fields.FIELD_SECTOR_ZONE_CITY)),
            expected_sale_price=self._as_int(deal.get(fields.FIELD_EXPECTED_SALE_PRICE)),
            registration_number=self.get_matricula(deal),
        )

    def update_property_listing(self, deal_id: str, listing: PropertyListing) -> None:
        """Actualiza en el deal solo los campos de `listing` que no son None."""
        updates: dict[str, Any] = {}

        if listing.property_type is not None:
            value = fields.PROPERTY_TYPE_VALUE_BY_NAME.get(listing.property_type)
            if value is not None:
                updates[fields.FIELD_PROPERTY_TYPE] = value
            else:
                logger.warning(
                    "Tipo de inmueble %r sin VALUE ID en PROPERTY_TYPE_VALUE_BY_NAME, no se actualiza en deal %s",
                    listing.property_type,
                    deal_id,
                )
        if listing.address is not None:
            updates[fields.FIELD_ADDRESS] = listing.address
        if listing.sector_zone_city is not None:
            updates[fields.FIELD_SECTOR_ZONE_CITY] = listing.sector_zone_city
        if listing.expected_sale_price is not None:
            updates[fields.FIELD_EXPECTED_SALE_PRICE] = listing.expected_sale_price
        if listing.registration_number is not None:
            updates[fields.FIELD_MATRICULA] = listing.registration_number

        if updates:
            self.update_deal(deal_id, updates)

    @staticmethod
    def _as_text(value: Any) -> str | None:
        return str(value) if value else None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _property_type_name(value: Any) -> str | None:
        try:
            value_int = int(value)
        except (TypeError, ValueError):
            return None
        for name, mapped_value in fields.PROPERTY_TYPE_VALUE_BY_NAME.items():
            if mapped_value == value_int:
                return name
        return None

    def update_deal(self, deal_id: str, fields: dict[str, Any]) -> None:
        """Actualiza campos de un deal de Bitrix. No lanza si falla.

        Un 200 de Bitrix no garantiza éxito: la API puede rechazar el campo/valor
        a nivel lógico y devolver igual HTTP 200 con `{"error": ...}` en el body
        — se detecta ese caso acá para no loguear como éxito una escritura que
        en realidad no aplicó.
        """
        try:
            response = requests.post(
                f"{self.webhook_url}crm.deal.update.json",
                json={"id": deal_id, "fields": fields},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and "error" in payload:
                logger.error(
                    "Bitrix rechazó la actualización del deal %s (%s): %s", deal_id, fields, payload
                )
                return
            logger.info("Deal %s actualizado: %s", deal_id, fields)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error actualizando deal %s: %s", deal_id, exc)

    def update_contact(self, contact_id: str, fields: dict[str, Any]) -> None:
        """Actualiza campos de un contacto de Bitrix. No lanza si falla."""
        try:
            response = requests.post(
                f"{self.webhook_url}crm.contact.update.json",
                json={"id": contact_id, "fields": fields},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info("Contacto %s actualizado: %s", contact_id, fields)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error actualizando contacto %s: %s", contact_id, exc)

    def update_contact_identity(self, contact_id: str, *, phone: str | None = None, full_name: str | None = None) -> None:
        """Actualiza nombre y/o teléfono de un contacto ya existente, solo lo que no es `None`.

        `full_name` se parte en `NAME` (primera palabra) y `LAST_NAME` (el
        resto) — es lo más cercano a "nombre y apellido" que la persona
        escribe en un chat de WhatsApp, sin pedirle que los separe.
        """
        updates: dict[str, Any] = {}

        if full_name:
            first, _, rest = full_name.partition(" ")
            updates["NAME"] = first
            if rest.strip():
                updates["LAST_NAME"] = rest.strip()
        if phone:
            updates["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "MOBILE"}]

        if updates:
            self.update_contact(contact_id, updates)
