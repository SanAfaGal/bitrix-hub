"""Fakes compartidos por los tests que no necesitan pegarle a un CRM de verdad.

`FakeCrmClient` implementa `app.crm.protocol.CrmClient` con datos en
memoria, configurables por deal/contacto — reemplaza las redefiniciones
locales de `FakeBitrixClient` que existían por archivo de test.
"""
from __future__ import annotations

from typing import Any

from app.crm.protocol import PropertyListing


class FakeCrmClient:
    def __init__(
        self,
        deals: dict[str, dict[str, Any]] | None = None,
        contacts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._deals = deals or {}
        self._contacts = contacts or {}
        self._next_comment_id = 1000
        self.comments: list[tuple[str, str]] = []
        self.pins: list[tuple[int, str]] = []
        self.duplicado_updates: list[tuple[str, bool]] = []
        self.authorization_status_updates: list[tuple[str, str]] = []
        self.uploaded_files: list[tuple[str, str, bytes]] = []
        self.upload_file_result: str | None = "https://example.bitrix24.com/docs/file/sample.pdf"

        # Bot de WhatsApp (experimental) — datos de inmueble por deal_id, y
        # contacto/deal por teléfono, configurables para simular ya-existe.
        self.property_listings: dict[str, PropertyListing] = {}
        self.property_listing_updates: list[tuple[str, PropertyListing]] = []
        self.contact_by_phone: dict[str, str] = {}
        self.contact_by_username: dict[str, str] = {}
        self.find_or_create_property_seller_contact_calls: list[tuple[str | None, str | None, str | None]] = []
        self.deal_by_contact: dict[str, str] = {}
        self._next_contact_id = 5000
        self._next_deal_id = 6000
        self.contact_identity_updates: list[tuple[str, str | None, str | None]] = []

        # Activo por defecto (mismo comportamiento default que BitrixClient
        # cuando el deal no tiene el campo seteado).
        self.bot_active: dict[str, bool] = {}
        self.bot_active_updates: list[tuple[str, bool]] = []

        # deal_ids que se simulan borrados en el CRM (deal_exists -> False).
        self.deleted_deals: set[str] = set()

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        return self._deals.get(deal_id, {})

    def deal_exists(self, deal_id: str) -> bool:
        return deal_id not in self.deleted_deals

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        return self._contacts.get(contact_id, {})

    def get_deal_contact_id(self, deal: dict[str, Any]) -> str | None:
        contact_id = deal.get("CONTACT_ID")
        return str(contact_id) if contact_id else None

    def get_contact_phone(self, contact: dict[str, Any]) -> str | None:
        phone = contact.get("PHONE")
        return phone if isinstance(phone, str) and phone.strip() else None

    def find_contact_by_phone(self, phone: str) -> dict[str, Any] | None:
        contact_id = self.contact_by_phone.get(phone)
        if contact_id is None:
            return None
        return self._contacts.get(contact_id)

    def get_contact_full_name(self, contact: dict[str, Any]) -> str | None:
        name = contact.get("NAME")
        last_name = contact.get("LAST_NAME")
        parts = [p.strip() for p in (name, last_name) if isinstance(p, str) and p.strip()]
        return " ".join(parts) if parts else None

    def get_matricula(self, deal: dict[str, Any]) -> str | None:
        matricula = deal.get("MATRICULA")
        return str(matricula) if matricula else None

    def set_duplicado_status(self, deal_id: str, has_duplicate: bool) -> None:
        self.duplicado_updates.append((deal_id, has_duplicate))

    def get_authorization_status(self, deal: dict[str, Any]) -> str | None:
        return deal.get("AUTHORIZATION_STATUS")

    def set_authorization_status(self, deal_id: str, status: str) -> None:
        self.authorization_status_updates.append((deal_id, status))

    def add_comment(self, deal_id: str, comment: str) -> int | None:
        self.comments.append((deal_id, comment))
        comment_id = self._next_comment_id
        self._next_comment_id += 1
        return comment_id

    def pin_comment(self, comment_id: int, deal_id: str) -> None:
        self.pins.append((comment_id, deal_id))

    def upload_file(self, folder_id: str, filename: str, content: bytes) -> str | None:
        self.uploaded_files.append((folder_id, filename, content))
        return self.upload_file_result

    def find_or_create_property_seller_contact(
        self, phone: str | None, username: str | None = None, display_name: str | None = None
    ) -> str | None:
        self.find_or_create_property_seller_contact_calls.append((phone, username, display_name))
        if phone and phone in self.contact_by_phone:
            return self.contact_by_phone[phone]
        if username and username in self.contact_by_username:
            return self.contact_by_username[username]
        if not phone:
            return None

        contact_id = str(self._next_contact_id)
        self._next_contact_id += 1
        if phone:
            self.contact_by_phone[phone] = contact_id
        if username:
            self.contact_by_username[username] = contact_id
        return contact_id

    def update_contact_identity(self, contact_id: str, *, phone: str | None = None, full_name: str | None = None) -> None:
        self.contact_identity_updates.append((contact_id, phone, full_name))
        contact = self._contacts.setdefault(contact_id, {})
        if phone:
            contact["PHONE"] = phone
        if full_name:
            contact["NAME"] = full_name

    def find_or_create_property_seller_deal(self, contact_id: str) -> str | None:
        if contact_id in self.deal_by_contact:
            return self.deal_by_contact[contact_id]
        deal_id = str(self._next_deal_id)
        self._next_deal_id += 1
        self.deal_by_contact[contact_id] = deal_id
        return deal_id

    def get_bot_active(self, deal_id: str) -> bool:
        return self.bot_active.get(deal_id, True)

    def set_bot_active(self, deal_id: str, active: bool) -> None:
        self.bot_active[deal_id] = active
        self.bot_active_updates.append((deal_id, active))

    def get_property_listing(self, deal_id: str) -> PropertyListing:
        return self.property_listings.get(deal_id, PropertyListing())

    def update_property_listing(self, deal_id: str, listing: PropertyListing) -> None:
        self.property_listing_updates.append((deal_id, listing))
        current = self.property_listings.get(deal_id, PropertyListing())
        self.property_listings[deal_id] = PropertyListing(
            property_type=listing.property_type if listing.property_type is not None else current.property_type,
            address=listing.address if listing.address is not None else current.address,
            sector_zone_city=(
                listing.sector_zone_city if listing.sector_zone_city is not None else current.sector_zone_city
            ),
            expected_sale_price=(
                listing.expected_sale_price
                if listing.expected_sale_price is not None
                else current.expected_sale_price
            ),
            registration_number=(
                listing.registration_number
                if listing.registration_number is not None
                else current.registration_number
            ),
        )
