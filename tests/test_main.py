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
