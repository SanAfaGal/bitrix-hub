from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import require_staff_user
from app.auth.settings import MicrosoftOAuthSettings
from app.main import app

_STAFF_USER = {"name": "Ana", "email": "ana@albertoalvarez.com"}
_ADMIN_USER = {"name": "Admin", "email": "admin@albertoalvarez.com"}

_SETTINGS = MicrosoftOAuthSettings(
    tenant_id="tenant",
    client_id="client",
    client_secret="secret",
    public_base_url="https://hub.example.com",
    admin_emails=("admin@albertoalvarez.com",),
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_override():
    yield
    app.dependency_overrides.pop(require_staff_user, None)


def test_home_redirects_to_login_when_not_authenticated(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login?next=/"


def test_home_shows_disabled_admin_card_for_non_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    app.dependency_overrides[require_staff_user] = lambda: _STAFF_USER
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)

    response = client.get("/")

    assert response.status_code == 200
    assert "Crear lead" in response.text
    assert 'href="/interno/nuevo-lead"' in response.text
    assert "home-card--disabled" in response.text
    assert 'href="/admin"' not in response.text


def test_home_shows_enabled_admin_card_for_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    app.dependency_overrides[require_staff_user] = lambda: _ADMIN_USER
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/admin"' in response.text
    assert "home-card--disabled" not in response.text
