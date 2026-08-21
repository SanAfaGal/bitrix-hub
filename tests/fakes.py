"""Fakes compartidos por los tests que no necesitan pegarle a un CRM de verdad.

`FakeCrmClient` implementa `app.crm.protocol.CrmClient` con datos en
memoria, configurables por deal/contacto — reemplaza las redefiniciones
locales de `FakeBitrixClient` que existían por archivo de test.
"""
from __future__ import annotations

from typing import Any


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
        self.welcome_sent_updates: list[str] = []
        self.uploaded_files: list[tuple[str, str, bytes]] = []
        self.upload_file_result: str | None = "https://example.bitrix24.com/docs/file/sample.pdf"

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        return self._deals.get(deal_id, {})

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        return self._contacts.get(contact_id, {})

    def get_deal_contact_id(self, deal: dict[str, Any]) -> str | None:
        contact_id = deal.get("CONTACT_ID")
        return str(contact_id) if contact_id else None

    def get_contact_phone(self, contact: dict[str, Any]) -> str | None:
        phone = contact.get("PHONE")
        return phone if isinstance(phone, str) and phone.strip() else None

    def get_matricula(self, deal: dict[str, Any]) -> str | None:
        matricula = deal.get("MATRICULA")
        return str(matricula) if matricula else None

    def set_duplicado_status(self, deal_id: str, has_duplicate: bool) -> None:
        self.duplicado_updates.append((deal_id, has_duplicate))

    def get_authorization_status(self, deal: dict[str, Any]) -> str | None:
        return deal.get("AUTHORIZATION_STATUS")

    def set_authorization_status(self, deal_id: str, status: str) -> None:
        self.authorization_status_updates.append((deal_id, status))

    def set_welcome_sent(self, deal_id: str) -> None:
        self.welcome_sent_updates.append(deal_id)

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
