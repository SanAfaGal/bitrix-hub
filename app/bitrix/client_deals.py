"""Mixin de `BitrixClient` (`app/bitrix/client.py`): deal — lectura/escritura cruda y campos de negocio.

Separado de `client.py` por el límite de 500 líneas del repo — ver el
docstring de `BitrixClient` para el resto del reparto (`client_contacts.py`,
`client_files.py`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from app.bitrix import fields
from app.bitrix._shared import REQUEST_TIMEOUT, error_detail
from app.crm.protocol import AuthorizationStatus, DealSource, PropertyListing

logger = logging.getLogger(__name__)


class DealsMixin:
    """Requiere `self.webhook_url` (ver `BitrixClient.__init__`)."""

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

    def get_deal_contact_id(self, deal: dict[str, Any]) -> str | None:
        """Extrae el ID del contacto vinculado a un deal (campo CONTACT_ID de Bitrix)."""
        contact_id = deal.get(fields.FIELD_CONTACT_ID)
        return str(contact_id) if contact_id else None

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

    def find_or_create_property_seller_deal(
        self, contact_id: str, title: str | None = None, source: DealSource | None = None
    ) -> str | None:
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
                error_detail(exc),
            )
            return None

        deal_fields: dict[str, Any] = {
            "CONTACT_ID": contact_id,
            "CATEGORY_ID": fields.CONSIGNACION_CATEGORY_ID,
            "TITLE": title or f"Consignación WhatsApp - contacto {contact_id}",
            fields.FIELD_FIRST_CONTACT: datetime.now(timezone.utc).isoformat(),
            fields.FIELD_BOT_ACTIVE: 1,
        }
        if source is not None:
            deal_fields[fields.FIELD_SOURCE] = fields.SOURCE_VALUE_BY_NAME[source]

        try:
            response = requests.post(
                f"{self.webhook_url}crm.deal.add.json",
                json={"fields": deal_fields},
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
                error_detail(exc),
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
