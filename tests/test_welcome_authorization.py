from __future__ import annotations

from app.flows.welcome_authorization import process_welcome_and_authorization


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
        self.calls: list[tuple[str, list[str], str | None]] = []

    def send_text_sequence(self, chat_id: str, messages: list[str], session: str | None = None) -> bool:
        self.calls.append((chat_id, messages, session))
        return self.sent


def test_sends_welcome_then_authorization_link_in_same_chat() -> None:
    bitrix = FakeBitrixClient(
        deal={"ID": "42", "CONTACT_ID": "7"},
        contact={"PHONE": [{"VALUE": "300 111 2233", "VALUE_TYPE": "MOBILE"}]},
    )
    waha = FakeWahaClient()

    result = process_welcome_and_authorization(
        "42", bitrix, waha, public_base_url="https://hub.example.com", session="default"
    )

    assert result == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}
    assert len(waha.calls) == 1
    chat_id, messages, session = waha.calls[0]
    assert chat_id == "573001112233@c.us"
    assert session == "default"
    assert len(messages) == 2
    assert "https://hub.example.com/formularios/autorizacion-de-corretaje?deal_id=42" in messages[1]


def test_returns_error_when_deal_has_no_contact() -> None:
    bitrix = FakeBitrixClient(deal={"ID": "42"})
    waha = FakeWahaClient()

    result = process_welcome_and_authorization("42", bitrix, waha, public_base_url="https://hub.example.com")

    assert result == {"ok": False, "deal_id": "42", "error": "El deal no tiene contacto vinculado"}
    assert waha.calls == []


def test_returns_error_when_phone_cannot_be_normalized() -> None:
    bitrix = FakeBitrixClient(
        deal={"ID": "42", "CONTACT_ID": "7"},
        contact={"PHONE": [{"VALUE": "123", "VALUE_TYPE": "MOBILE"}]},
    )
    waha = FakeWahaClient()

    result = process_welcome_and_authorization("42", bitrix, waha, public_base_url="https://hub.example.com")

    assert result == {
        "ok": False,
        "deal_id": "42",
        "contact_id": "7",
        "error": "Teléfono inválido: 123",
    }
    assert waha.calls == []


def test_propagates_waha_failure() -> None:
    bitrix = FakeBitrixClient(
        deal={"ID": "42", "CONTACT_ID": "7"},
        contact={"PHONE": [{"VALUE": "3001112233", "VALUE_TYPE": "MOBILE"}]},
    )
    waha = FakeWahaClient(sent=False)

    result = process_welcome_and_authorization("42", bitrix, waha, public_base_url="https://hub.example.com")

    assert result["ok"] is False
    assert result["chat_id"] == "573001112233@c.us"
