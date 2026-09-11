from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.interno.router as interno_router
from app.auth.deps import require_staff_user
from app.main import app
from app.shared import idempotency
from tests.fakes import FakeCrmClient

_STAFF_USER = {"name": "Ana", "email": "ana@albertoalvarez.com"}


@pytest.fixture(autouse=True)
def _reset_idempotency_tokens() -> None:
    idempotency._used_tokens.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_override():
    yield
    app.dependency_overrides.pop(require_staff_user, None)


def _log_in() -> None:
    app.dependency_overrides[require_staff_user] = lambda: _STAFF_USER


def _form_data(**overrides) -> dict:
    defaults = dict(
        interested_party="Ana Pérez",
        owner_phone="3001112233",
        email="",
        property_type="Apartamento",
        address="Calle 10 # 20-30",
        location="El Poblado, Medellín",
        location_sector_code="00081",
        sale_price="",
        coverage_override="",
        idempotency_token="tok-1",
    )
    defaults.update(overrides)
    return defaults


def test_get_nuevo_lead_requires_login(client: TestClient) -> None:
    response = client.get("/interno/nuevo-lead", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login?next=/interno/nuevo-lead"


def test_get_nuevo_lead_shows_form_when_authenticated(client: TestClient) -> None:
    _log_in()

    response = client.get("/interno/nuevo-lead")

    assert response.status_code == 200
    assert "Nuevo lead" in response.text
    assert 'name="idempotency_token"' in response.text


def test_post_nuevo_lead_creates_lead_and_redirects(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in()
    fake_crm = FakeCrmClient()
    monkeypatch.setattr(interno_router, "get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.coverage.get_sector_coverage", lambda sector_code: True)

    response = client.post("/interno/nuevo-lead", data=_form_data(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/interno/lead/")
    assert len(fake_crm.find_or_create_property_seller_deal_calls) == 1


def test_post_nuevo_lead_blocked_by_coverage_shows_warning(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in()
    fake_crm = FakeCrmClient()
    monkeypatch.setattr(interno_router, "get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.coverage.get_sector_coverage", lambda sector_code: False)

    response = client.post("/interno/nuevo-lead", data=_form_data(), follow_redirects=False)

    assert response.status_code == 200
    assert "fuera de la zona de cobertura" in response.text
    assert 'name="coverage_override"' in response.text
    assert fake_crm.find_or_create_property_seller_deal_calls == []


def test_post_nuevo_lead_with_override_creates_lead_and_records_exception(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _log_in()
    fake_crm = FakeCrmClient()
    monkeypatch.setattr(interno_router, "get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.forms.coverage.get_sector_coverage", lambda sector_code: False)

    response = client.post(
        "/interno/nuevo-lead", data=_form_data(coverage_override="true"), follow_redirects=False
    )

    assert response.status_code == 303
    assert len(fake_crm.comments) == 1
    assert "ana@albertoalvarez.com" in fake_crm.comments[0][1]


def test_post_nuevo_lead_rejects_invalid_data(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in()
    fake_crm = FakeCrmClient()
    monkeypatch.setattr(interno_router, "get_crm_client", lambda: fake_crm)

    response = client.post("/interno/nuevo-lead", data=_form_data(owner_phone="123"), follow_redirects=False)

    assert response.status_code == 200
    assert "inválido" in response.text.lower()
    assert fake_crm.find_or_create_property_seller_deal_calls == []


def test_get_lead_detail_shows_summary(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in()
    fake_crm = FakeCrmClient(
        deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}},
        contacts={"5000": {"NAME": "Ana", "LAST_NAME": "Pérez"}},
    )
    from app.crm.protocol import PropertyListing

    fake_crm.property_listings["6000"] = PropertyListing(property_type="Apartamento", address="Calle 10 # 20-30")
    monkeypatch.setattr(interno_router, "get_crm_client", lambda: fake_crm)

    response = client.get("/interno/lead/6000")

    assert response.status_code == 200
    assert "Ana Pérez" in response.text
    assert "Calle 10 # 20-30" in response.text


def test_get_lead_detail_404_when_deal_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in()
    fake_crm = FakeCrmClient()
    fake_crm.deleted_deals.add("9999")
    monkeypatch.setattr(interno_router, "get_crm_client", lambda: fake_crm)

    response = client.get("/interno/lead/9999")

    assert response.status_code == 404
