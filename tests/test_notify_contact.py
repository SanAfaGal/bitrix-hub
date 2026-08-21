from __future__ import annotations

from app.flows.notify_contact import process_notify_contact
from tests.fakes import FakeCrmClient


class FakeWahaClient:
    def __init__(self, sent: bool = True) -> None:
        self.sent = sent
        self.calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.sent


def test_process_notify_contact_sends_to_normalized_phone() -> None:
    crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "300 111 2233"}},
    )
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", crm, waha, session="default")

    assert result == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}
    assert waha.calls == [("573001112233@c.us", "hola", "default")]


def test_process_notify_contact_returns_error_when_deal_has_no_contact() -> None:
    crm = FakeCrmClient(deals={"42": {"ID": "42"}})
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", crm, waha)

    assert result == {"ok": False, "deal_id": "42", "error": "El deal no tiene contacto vinculado"}
    assert waha.calls == []


def test_process_notify_contact_returns_error_when_contact_has_no_phone() -> None:
    crm = FakeCrmClient(deals={"42": {"ID": "42", "CONTACT_ID": "7"}}, contacts={"7": {}})
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", crm, waha)

    assert result == {"ok": False, "deal_id": "42", "contact_id": "7", "error": "El contacto no tiene teléfono"}
    assert waha.calls == []


def test_process_notify_contact_returns_error_when_phone_cannot_be_normalized() -> None:
    crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "123"}},
    )
    waha = FakeWahaClient()

    result = process_notify_contact("42", "hola", crm, waha)

    assert result == {"ok": False, "deal_id": "42", "contact_id": "7", "error": "Teléfono inválido: 123"}
    assert waha.calls == []


def test_process_notify_contact_propagates_waha_failure() -> None:
    crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "3001112233"}},
    )
    waha = FakeWahaClient(sent=False)

    result = process_notify_contact("42", "hola", crm, waha)

    assert result["ok"] is False
    assert result["chat_id"] == "573001112233@c.us"
