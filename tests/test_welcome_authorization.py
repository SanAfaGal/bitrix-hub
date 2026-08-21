from __future__ import annotations

from app.flows.welcome_authorization import process_welcome_and_authorization
from tests.fakes import FakeCrmClient


class FakeWahaClient:
    def __init__(self, sent: bool = True) -> None:
        self.sent = sent
        self.calls: list[tuple[str, list[str], str | None]] = []

    def send_text_sequence(self, chat_id: str, messages: list[str], session: str | None = None) -> bool:
        self.calls.append((chat_id, messages, session))
        return self.sent


def test_sends_welcome_then_authorization_link_in_same_chat() -> None:
    crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "300 111 2233"}},
    )
    waha = FakeWahaClient()

    result = process_welcome_and_authorization(
        "42", crm, waha, public_base_url="https://hub.example.com", session="default"
    )

    assert result == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}
    assert len(waha.calls) == 1
    chat_id, messages, session = waha.calls[0]
    assert chat_id == "573001112233@c.us"
    assert session == "default"
    assert len(messages) == 2
    assert "https://hub.example.com/formularios/autorizacion-de-corretaje?deal_id=42" in messages[1]


def test_returns_error_when_deal_has_no_contact() -> None:
    crm = FakeCrmClient(deals={"42": {"ID": "42"}})
    waha = FakeWahaClient()

    result = process_welcome_and_authorization("42", crm, waha, public_base_url="https://hub.example.com")

    assert result == {"ok": False, "deal_id": "42", "error": "El deal no tiene contacto vinculado"}
    assert waha.calls == []


def test_returns_error_when_phone_cannot_be_normalized() -> None:
    crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "123"}},
    )
    waha = FakeWahaClient()

    result = process_welcome_and_authorization("42", crm, waha, public_base_url="https://hub.example.com")

    assert result == {
        "ok": False,
        "deal_id": "42",
        "contact_id": "7",
        "error": "Teléfono inválido: 123",
    }
    assert waha.calls == []


def test_propagates_waha_failure() -> None:
    crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "3001112233"}},
    )
    waha = FakeWahaClient(sent=False)

    result = process_welcome_and_authorization("42", crm, waha, public_base_url="https://hub.example.com")

    assert result["ok"] is False
    assert result["chat_id"] == "573001112233@c.us"
