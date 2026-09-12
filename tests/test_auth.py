from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

import app.auth.router as auth_router_module
from app.auth import client as auth_client
from app.auth.deps import current_staff_user, is_admin_email, log_in, log_out, require_admin, require_staff_user
from app.auth.settings import MicrosoftOAuthSettings
from app.main import app

_SETTINGS = MicrosoftOAuthSettings(
    tenant_id="tenant-1",
    client_id="client-1",
    client_secret="secret-1",
    public_base_url="https://hub.example.com",
    allowed_domains=(),
    admin_emails=("admin@albertoalvarez.com",),
)


class _FakeSessionRequest:
    """Doble mínimo de `Request` con `.session` como dict — alcanza para
    ejercitar `deps.py` sin levantar un TestClient."""

    def __init__(self, session: dict | None = None, path: str = "/interno/nuevo-lead") -> None:
        self.session = session or {}
        self.url = type("_URL", (), {"path": path})()


# ── deps.py ──────────────────────────────────────────────────────────────


def test_current_staff_user_returns_none_without_session() -> None:
    request = _FakeSessionRequest()
    assert current_staff_user(request) is None


def test_log_in_then_current_staff_user_roundtrip() -> None:
    request = _FakeSessionRequest()
    log_in(request, name="Ana", email="ana@albertoalvarez.com")

    assert current_staff_user(request) == {"name": "Ana", "email": "ana@albertoalvarez.com"}


def test_log_out_clears_session() -> None:
    request = _FakeSessionRequest(session={"staff_user": {"name": "Ana", "email": "ana@albertoalvarez.com"}})
    log_out(request)

    assert current_staff_user(request) is None


def test_require_staff_user_redirects_when_not_authenticated() -> None:
    request = _FakeSessionRequest(path="/interno/nuevo-lead")

    with pytest.raises(HTTPException) as exc_info:
        require_staff_user(request)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 303
    assert exc_info.value.headers["Location"] == "/auth/login?next=/interno/nuevo-lead"


def test_require_staff_user_returns_user_when_authenticated() -> None:
    request = _FakeSessionRequest(session={"staff_user": {"name": "Ana", "email": "ana@albertoalvarez.com"}})

    assert require_staff_user(request) == {"name": "Ana", "email": "ana@albertoalvarez.com"}  # type: ignore[arg-type]


def test_require_admin_redirects_when_not_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)
    request = _FakeSessionRequest()

    with pytest.raises(HTTPException) as exc_info:
        require_admin(request)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 303


def test_require_admin_forbids_authenticated_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)
    request = _FakeSessionRequest(session={"staff_user": {"name": "Ana", "email": "ana@albertoalvarez.com"}})

    with pytest.raises(HTTPException) as exc_info:
        require_admin(request)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


def test_require_admin_allows_email_in_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)
    request = _FakeSessionRequest(session={"staff_user": {"name": "Admin", "email": "admin@albertoalvarez.com"}})

    assert require_admin(request) == "admin@albertoalvarez.com"  # type: ignore[arg-type]


def test_require_admin_allowlist_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)
    request = _FakeSessionRequest(session={"staff_user": {"name": "Admin", "email": "ADMIN@albertoalvarez.com"}})

    assert require_admin(request) == "ADMIN@albertoalvarez.com"  # type: ignore[arg-type]


def test_is_admin_email_true_for_allowlisted_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)

    assert is_admin_email("ADMIN@albertoalvarez.com") is True


def test_is_admin_email_false_for_non_allowlisted_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", lambda: _SETTINGS)

    assert is_admin_email("ana@albertoalvarez.com") is False


def test_is_admin_email_false_when_oauth_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise() -> None:
        raise RuntimeError("Faltan variables de entorno")

    monkeypatch.setattr("app.auth.settings.load_microsoft_oauth_settings", _raise)

    assert is_admin_email("admin@albertoalvarez.com") is False


# ── client.py ────────────────────────────────────────────────────────────


def test_check_allowed_domain_noop_when_no_domains_configured() -> None:
    auth_client.check_allowed_domain("ana@gmail.com", ())  # no lanza


def test_check_allowed_domain_rejects_disallowed_domain() -> None:
    with pytest.raises(auth_client.MicrosoftAuthError):
        auth_client.check_allowed_domain("ana@gmail.com", ("albertoalvarez.com",))


def test_check_allowed_domain_allows_matching_domain() -> None:
    auth_client.check_allowed_domain("ana@albertoalvarez.com", ("albertoalvarez.com",))  # no lanza


def test_build_authorize_url_includes_state_and_select_account() -> None:
    url = auth_client.build_authorize_url(
        tenant_id="t1", client_id="c1", redirect_uri="https://hub.example.com/auth/callback", state="abc123"
    )
    assert "login.microsoftonline.com/t1/oauth2/v2.0/authorize" in url
    assert "state=abc123" in url
    assert "prompt=select_account" in url


def test_build_logout_url() -> None:
    url = auth_client.build_logout_url(tenant_id="t1", post_logout_redirect_uri="https://hub.example.com/auth/login")
    assert "login.microsoftonline.com/t1/oauth2/v2.0/logout" in url


# ── router.py (TestClient, settings monkeypatcheadas) ──────────────────


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.shared import rate_limit as rate_limit_module

    rate_limit_module._hits.clear()
    monkeypatch.setattr(auth_router_module, "load_microsoft_oauth_settings", lambda: _SETTINGS)
    return TestClient(app)


def test_login_redirects_to_microsoft(client: TestClient) -> None:
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 302
    assert "login.microsoftonline.com" in response.headers["location"]


def test_login_rejects_open_redirect_next(client: TestClient) -> None:
    response = client.get("/auth/login?next=https://evil.example.com", follow_redirects=False)

    assert response.status_code == 302  # sigue redirigiendo a Microsoft normal


def test_callback_rejects_missing_state(client: TestClient) -> None:
    response = client.get("/auth/callback?code=abc", follow_redirects=False)

    assert response.status_code == 400


def test_callback_rejects_mismatched_state(client: TestClient) -> None:
    client.get("/auth/login", follow_redirects=False)  # siembra oauth_state en la sesión

    response = client.get("/auth/callback?code=abc&state=wrong-state", follow_redirects=False)

    assert response.status_code == 400


def test_callback_success_logs_in_and_redirects_to_next(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login_response = client.get("/auth/login?next=/interno/nuevo-lead", follow_redirects=False)
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    monkeypatch.setattr(auth_router_module, "exchange_code_for_token", lambda **kw: "fake-access-token")
    monkeypatch.setattr(
        auth_router_module, "fetch_user_profile", lambda token: {"name": "Ana", "email": "ana@albertoalvarez.com"}
    )

    response = client.get(f"/auth/callback?code=abc123&state={state}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/interno/nuevo-lead"


def test_callback_rejects_disallowed_domain(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_with_domain = MicrosoftOAuthSettings(
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="secret-1",
        public_base_url="https://hub.example.com",
        allowed_domains=("albertoalvarez.com",),
        admin_emails=(),
    )
    monkeypatch.setattr(auth_router_module, "load_microsoft_oauth_settings", lambda: settings_with_domain)
    login_response = client.get("/auth/login", follow_redirects=False)
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    monkeypatch.setattr(auth_router_module, "exchange_code_for_token", lambda **kw: "fake-access-token")
    monkeypatch.setattr(
        auth_router_module, "fetch_user_profile", lambda token: {"name": "Ana", "email": "ana@gmail.com"}
    )

    response = client.get(f"/auth/callback?code=abc123&state={state}", follow_redirects=False)

    assert response.status_code == 400


def test_logout_clears_session_and_redirects_to_microsoft_logout(client: TestClient) -> None:
    response = client.post("/auth/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "login.microsoftonline.com" in response.headers["location"]
