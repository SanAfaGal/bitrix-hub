"""Mixin de `BitrixClient` (`app/bitrix/client.py`): contacto — lectura, búsqueda y creación.

Separado de `client.py` por el límite de 500 líneas del repo — ver el
docstring de `BitrixClient` para el resto del reparto (`client_deals.py`,
`client_files.py`).
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from app.bitrix import fields
from app.bitrix._shared import REQUEST_TIMEOUT, BitrixLookupError, error_detail, normalize_person_name
from app.shared.phone_countries import PHONE_COUNTRIES

logger = logging.getLogger(__name__)

# Tipos de teléfono de Bitrix, en orden de preferencia para notificar por WhatsApp.
_PREFERRED_PHONE_TYPES = ("MOBILE", "WORK", "HOME", "OTHER")

# Indicativos conocidos (`app.shared.phone_countries`, dataset de `phonenumbers`),
# del más largo al más corto — usado en `_find_duplicates_by_phone` para
# reconocer con cuál indicativo empieza un teléfono, sin importar el país
# (antes solo se reconocía "57"). Se prueba el más largo primero para no
# recortar de más con uno más corto que también matchee el prefijo (ej. "1").
_KNOWN_CALLING_CODES: tuple[str, ...] = tuple(
    sorted({country["code"] for country in PHONE_COUNTRIES}, key=len, reverse=True)
)


class ContactsMixin:
    """Requiere `self.webhook_url` y `self.get_contact` (ver `BitrixClient.__init__`/`client_deals.py`)."""

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Obtiene los campos de un contacto de Bitrix. Retorna {} si la llamada falla."""
        try:
            response = self.session.get(
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

    def get_contact_email(self, contact: dict[str, Any]) -> str | None:
        """Extrae el primer email disponible del campo EMAIL de un contacto de Bitrix.

        Mismo formato de lista que PHONE (`{"VALUE": "...", "VALUE_TYPE": "..."}`)
        pero sin un tipo preferido — a diferencia del teléfono, acá no importa
        cuál, solo si hay alguno.
        """
        emails = contact.get("EMAIL")
        if not isinstance(emails, list) or not emails:
            return None
        for entry in emails:
            if not isinstance(entry, dict):
                continue
            value = entry.get("VALUE")
            if isinstance(value, str) and value.strip():
                return value
        return None

    def find_contact_by_phone(self, phone: str) -> dict[str, Any] | None:
        """Busca un contacto ya existente en Bitrix para `phone`. Retorna sus campos, o None si no hay match.

        Usado para decidir la plantilla de bienvenida del bot de WhatsApp
        (cliente conocido vs. desconocido) — reusa la misma búsqueda de
        duplicados que `find_or_create_property_seller_contact`, pero nunca
        crea nada.
        """
        try:
            contact_id, _ = self._find_duplicates_by_phone(phone)
        except BitrixLookupError:
            return None
        if contact_id is None:
            return None
        return self.get_contact(contact_id) or None

    def get_contact_full_name(self, contact: dict[str, Any]) -> str | None:
        """Extrae el nombre completo (NAME + LAST_NAME) de un contacto de Bitrix."""
        name = contact.get("NAME")
        last_name = contact.get("LAST_NAME")
        parts = [p.strip() for p in (name, last_name) if isinstance(p, str) and p.strip()]
        return " ".join(parts) if parts else None

    def find_or_create_property_seller_contact(
        self,
        phone: str | None,
        username: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
    ) -> str | None:
        """Busca un contacto por teléfono (o por `username` si no hay teléfono); si no existe, lo crea.

        `username` cubre el caso de un remitente de WhatsApp con el número
        oculto (chat `@lid`, ver `app.waha.phone.lid_from_chat_id`) — se
        guarda en `fields.FIELD_LINK_ID`, no reemplaza al teléfono. El
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
        except BitrixLookupError:
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

        return self._create_contact(phone, username, display_name, email)

    def _find_duplicates_by_phone(self, phone: str) -> tuple[str | None, str | None]:
        """Busca contacto y lead existentes para `phone` en una sola llamada a Bitrix.

        Retorna `(contact_id, lead_id)` — cualquiera puede ser `None`. El
        lead importa aunque haya contacto: `find_or_create_property_seller_contact`
        solo lo usa cuando no hay contacto (ver ahí). Lanza `BitrixLookupError`
        si falla la llamada.

        `crm.duplicate.findbycomm` compara el valor tal cual está guardado —
        no normaliza. Los contactos nuevos se guardan con `+` delante
        (`_create_contact`) y hay contactos viejos guardados en formato
        local (sin indicativo) o sin `+`; y el propio `phone` que llega acá
        puede venir con indicativo (WhatsApp, vía `to_chat_id`) o sin él
        (formulario interno, que para Colombia lo manda sin `57` a propósito
        — ver `NuevoLeadPayload.full_phone`). El indicativo de por medio no
        es solo el de Colombia — cualquier contacto, de cualquier país,
        puede estar guardado con o sin el suyo — así que si `phone` empieza
        con alguno de los indicativos conocidos (`_KNOWN_CALLING_CODES`), se
        agrega también la variante local (indicativo quitado); si no trae
        ninguno y tiene pinta de número local (10 dígitos, la mayoría de
        leads son de Colombia), se prueba además con `57` delante. Ninguna
        combinación cubre el 100% de los casos (un contacto de otro país
        guardado en formato local, sin indicativo, no se detecta) — si no,
        un contacto con alguno de esos formatos no aparece acá, Bitrix lo
        crea igual y su propio control de duplicados (que sí normaliza) lo
        borra después.
        """
        values = [phone, f"+{phone}"]
        # `len(phone) > 10` (no solo `> len(code)`) importa: un número local de
        # Colombia de 10 dígitos empieza casi siempre por "3xx" (celular), que
        # por pura coincidencia de dígitos matchea el indicativo real de varios
        # países (30=Grecia, 34=España, ...) — sin este piso, un bare local
        # cualquiera se leería como si trajera indicativo y se le recortarían
        # mal los primeros dígitos.
        matched_code = next(
            (code for code in _KNOWN_CALLING_CODES if phone.startswith(code) and len(phone) > 10), None
        )
        if matched_code is not None:
            local = phone[len(matched_code) :]
            values += [local, f"+{local}"]
        elif len(phone) == 10:
            values += [f"57{phone}", f"+57{phone}"]

        try:
            response = self.session.post(
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
            logger.error("Error buscando duplicados por teléfono %s en Bitrix: %s%s", phone, exc, error_detail(exc))
            raise BitrixLookupError from exc

    def _find_contact_by_username(self, username: str) -> str | None:
        """Retorna el contact_id si hay match, o None si no hay ninguno. Lanza `BitrixLookupError` si falla la llamada."""
        try:
            response = self.session.post(
                f"{self.webhook_url}crm.contact.list.json",
                json={"filter": {fields.FIELD_LINK_ID.uf_crm: username}, "select": ["ID"]},
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
                "Error buscando contacto por username %s en Bitrix: %s%s", username, exc, error_detail(exc)
            )
            raise BitrixLookupError from exc

    def _create_contact(
        self, phone: str | None, username: str | None, display_name: str | None, email: str | None = None
    ) -> str | None:
        contact_fields: dict[str, Any] = {"NAME": normalize_person_name(display_name) or "Contacto WhatsApp"}
        if phone:
            phone_value = phone if phone.startswith("+") else f"+{phone}"
            contact_fields["PHONE"] = [{"VALUE": phone_value, "VALUE_TYPE": "MOBILE"}]
        if username:
            contact_fields[fields.FIELD_LINK_ID.uf_crm] = username
        if email:
            contact_fields["EMAIL"] = [{"VALUE": email, "VALUE_TYPE": "WORK"}]

        try:
            response = self.session.post(
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
                "Error creando contacto para %s en Bitrix: %s%s", phone or username, exc, error_detail(exc)
            )
            return None

    def update_contact(self, contact_id: str, fields: dict[str, Any]) -> None:
        """Actualiza campos de un contacto de Bitrix. No lanza si falla."""
        try:
            response = self.session.post(
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
            normalized = normalize_person_name(full_name)
            first, _, rest = normalized.partition(" ")
            updates["NAME"] = first
            if rest.strip():
                updates["LAST_NAME"] = rest.strip()
        if phone:
            updates["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "MOBILE"}]

        if updates:
            self.update_contact(contact_id, updates)
