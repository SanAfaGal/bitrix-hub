from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.xposure.deps import get_xposure_client
from app.xposure.models import PropertySearchResult

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_single_property_lookup() -> None:
    class FakeClient:
        def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None) -> PropertySearchResult:
            assert tax_roll == "12345"
            return PropertySearchResult(tax_roll=tax_roll, exists=True, mls="987654")

    app.dependency_overrides[get_xposure_client] = lambda: FakeClient()
    try:
        response = client.get("/properties/12345")
    finally:
        app.dependency_overrides.pop(get_xposure_client, None)

    assert response.status_code == 200
    assert response.json()["mls"] == "987654"


def test_webhook_deal_event_delegates_to_flow(monkeypatch) -> None:
    class FakeBitrixClient:
        def get_deal(self, deal_id: str) -> dict:
            return {"ID": deal_id}

        def add_comment(self, *args, **kwargs) -> int:
            return 1

        def pin_comment(self, *args, **kwargs) -> None:
            return None

        def update_deal(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr("app.flows.router.get_bitrix_client", lambda: FakeBitrixClient())
    monkeypatch.setattr("app.flows.router.get_xposure_client", lambda: None)

    response = client.post("/webhook/deal-event", data={"data[FIELDS][ID]": "42"})
    assert response.status_code == 200
    assert response.json()["deal_id"] == "42"


def test_webhook_deal_stage_broker_auth_sends_welcome_and_link(monkeypatch) -> None:
    class FakeBitrixClient:
        def get_deal(self, deal_id: str) -> dict:
            return {"ID": deal_id, "CONTACT_ID": "7"}

        def get_contact(self, contact_id: str) -> dict:
            return {"PHONE": [{"VALUE": "3001112233", "VALUE_TYPE": "MOBILE"}]}

    class FakeWahaClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str], str | None]] = []

        def send_text_sequence(self, chat_id: str, messages: list[str], session: str | None = None) -> bool:
            self.calls.append((chat_id, messages, session))
            return True

    monkeypatch.setattr("app.flows.router.get_bitrix_client", lambda: FakeBitrixClient())
    monkeypatch.setattr("app.flows.router.get_waha_client", lambda: FakeWahaClient())
    monkeypatch.setattr("app.flows.router.load_public_base_url", lambda: "https://hub.example.com")

    response = client.post("/webhook/deal-stage-broker-auth", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}


def test_webhook_deal_stage_broker_auth_requires_deal_id() -> None:
    response = client.post("/webhook/deal-stage-broker-auth", data={})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Falta ID"}


def test_webhook_deal_stage_broker_auth_logs_error_when_public_base_url_missing(monkeypatch, caplog) -> None:
    class FakeBitrixClient:
        def get_deal(self, deal_id: str) -> dict:
            return {"ID": deal_id}

    def raise_missing_public_base_url():
        raise RuntimeError("Falta variable de entorno: HUB_PUBLIC_BASE_URL")

    monkeypatch.setattr("app.flows.router.get_bitrix_client", lambda: FakeBitrixClient())
    monkeypatch.setattr("app.flows.router.get_waha_client", lambda: object())
    monkeypatch.setattr("app.flows.router.load_public_base_url", raise_missing_public_base_url)

    with caplog.at_level("ERROR"):
        response = client.post("/webhook/deal-stage-broker-auth", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Falta variable de entorno: HUB_PUBLIC_BASE_URL"}
    assert any("42" in record.message and "HUB_PUBLIC_BASE_URL" in record.message for record in caplog.records)
