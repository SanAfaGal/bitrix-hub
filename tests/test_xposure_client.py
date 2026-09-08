from __future__ import annotations

import pytest
import requests

from app.xposure.client import XposureClient

_BASE_URL = "https://xposure.example.com"


def _client() -> XposureClient:
    return XposureClient(_BASE_URL, "user", "pass")


class _FakeResponse:
    def __init__(self, text: str = "", url: str = "", status_code: int = 200) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_login_succeeds_when_redirect_leaves_login_page(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(client, "_get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(url=f"{_BASE_URL}/portal/colombia/Home"))

    client.login()  # No debe lanzar.


def test_login_raises_when_still_on_login_page(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(client, "_get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(url=f"{_BASE_URL}/portal/Login"))

    with pytest.raises(RuntimeError, match="No se pudo iniciar sesión"):
        client.login()


def test_search_property_returns_not_exists_when_no_results(monkeypatch) -> None:
    client = _client()
    html = '<div id="total-listings-count">0</div>'
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(text=html))

    result = client.search_property("12345")

    assert result.exists is False
    assert result.tax_roll == "12345"
    assert result.reason == "No se encontraron resultados"


def test_search_property_returns_exists_without_mls_when_not_found_in_page(monkeypatch) -> None:
    client = _client()
    html = '<div id="total-listings-count">1</div><div>Sin MLS acá</div>'
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(text=html))

    result = client.search_property("12345")

    assert result.exists is True
    assert result.mls is None
    assert result.reason == "No se encontró MLS en la página"


def test_search_property_extracts_mls_and_builds_detail_url(monkeypatch) -> None:
    client = _client()
    html = '<div id="total-listings-count">1</div><div>Ficha MLS# 238899 disponible</div>'
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(text=html))

    result = client.search_property("12345")

    assert result.exists is True
    assert result.mls == "238899"
    assert result.url == f"{_BASE_URL}/portal/colombia/ViewDetail?mlsForDisplay=238899"


def test_search_property_raises_on_http_error(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(status_code=500))

    with pytest.raises(requests.HTTPError):
        client.search_property("12345")
