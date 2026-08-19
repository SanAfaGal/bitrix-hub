from __future__ import annotations

from app.flows.notify_contact import process_notify_contact


class FakeBitrixClient:
    def __init__(self, deal: dict, contact: dict | None = None) -> None:
        self._deal = deal
        self._contact = contact or {}

    def get_deal(self, deal_id: str) -> dict:
        return self._deal

    def get_contact(self, contact_id: str) -> dict:
        assert contact_id == self._deal.get("CONTACT_ID")
        return self._contact


class FakeWahaClient:
    def __init__(self, sent: bool = True) -> None:
        self.sent = sent
        self.calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.sent


def test_process_notify_contact_sends_to_normalized_phone() -> None:
    bitrix = FakeBitrixClient(
        deal={"ID": "42", "CONTACT_ID": "7"},
        contact={"PHONE": [{"VALUE": "300 111 2233", "VALUE_TYPE": "MOBILE"}]},
    )
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", bitrix, waha, session="default")

    assert result == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}
    assert waha.calls == [("573001112233@c.us", "hola", "default")]


def test_process_notify_contact_returns_error_when_deal_has_no_contact() -> None:
    bitrix = FakeBitrixClient(deal={"ID": "42"})
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", bitrix, waha)

    assert result == {"ok": False, "deal_id": "42", "error": "El deal no tiene contacto vinculado"}
    assert waha.calls == []


def test_process_notify_contact_returns_error_when_contact_has_no_phone() -> None:
    bitrix = FakeBitrixClient(deal={"ID": "42", "CONTACT_ID": "7"}, contact={})
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", bitrix, waha)

    assert result == {"ok": False, "deal_id": "42", "contact_id": "7", "error": "El contacto no tiene teléfono"}
    assert waha.calls == []


def test_process_notify_contact_returns_error_when_phone_cannot_be_normalized() -> None:
    bitrix = FakeBitrixClient(
        deal={"ID": "42", "CONTACT_ID": "7"},
        contact={"PHONE": [{"VALUE": "123", "VALUE_TYPE": "MOBILE"}]},
    )
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", bitrix, waha)

    assert result == {"ok": False, "deal_id": "42", "contact_id": "7", "error": "Teléfono inválido: 123"}
    assert waha.calls == []


def test_process_notify_contact_propagates_waha_failure() -> None:
    bitrix = FakeBitrixClient(
        deal={"ID": "42", "CONTACT_ID": "7"},
        contact={"PHONE": [{"VALUE": "3001112233", "VALUE_TYPE": "MOBILE"}]},
    )
    waha = FakeWahaClient(sent=False)

    result = process_notify_contact("42", "hola", bitrix, waha)

    assert result["ok"] is False
    assert result["chat_id"] == "573001112233@c.us"
