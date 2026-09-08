from __future__ import annotations

import pytest
import requests

import app.xposure.client as xposure_client_module
from app.xposure.client import XposureClient

_BASE_URL = "https://xposure.example.com"


def _client() -> XposureClient:
    return XposureClient(_BASE_URL, "user", "pass")


@pytest.fixture(autouse=True)
def _reset_area_code_cache():
    # resolve_area_code cachea a nivel de módulo (ver client.py) — sin esto,
    # un test dejaría el catálogo cacheado para el siguiente y se filtrarían
    # resultados entre pruebas.
    xposure_client_module._area_code_cache = None
    yield
    xposure_client_module._area_code_cache = None


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


def test_search_property_filters_by_status_activo_opcionado(monkeypatch) -> None:
    # Sin este filtro, Xposure busca en todos los estados (incluye Cancelado,
    # Vendido, Vencido, ...) y encuentra falsos positivos: un inmueble que ya
    # no está publicado no debería bloquear una nueva Autorización de
    # Corretaje. El formulario real de búsqueda trae "Activo" (1) y
    # "Opcionado" (3) preseleccionados — mismo criterio acá.
    client = _client()
    html = '<div id="total-listings-count">0</div>'
    captured: dict = {}

    def fake_post(path, data=None, **kwargs):
        captured["data"] = data
        return _FakeResponse(text=html)

    monkeypatch.setattr(client, "_post", fake_post)

    client.search_property("12345")

    assert captured["data"]["status"] == ["1", "3"]


def test_search_property_raises_on_http_error(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(client, "_post", lambda *a, **k: _FakeResponse(status_code=500))

    with pytest.raises(requests.HTTPError):
        client.search_property("12345")


_AREA_CODE_FORM_HTML = """
<select name="tax_roll_area_code" class="form-control" multiple>
  <option value=" " selected>Buscar Todos</option>
  <option value="7" title="Proyecto nuevo">Proyecto nuevo</option>
  <option value="2" title="001N">001N</option>
  <option value="36" title="50C">50C</option>
</select>
"""


def test_resolve_area_code_returns_internal_id(monkeypatch) -> None:
    # tax_roll_area_code no es el código de oficina en texto: es el id
    # interno de un <select> del formulario real de búsqueda, sin relación
    # con el texto visible (confirmado en vivo contra Xposure — "001N" -> "2",
    # "50C" -> "36").
    client = _client()
    monkeypatch.setattr(client, "_get", lambda *a, **k: _FakeResponse(text=_AREA_CODE_FORM_HTML))

    assert client.resolve_area_code("001N") == "2"
    assert client.resolve_area_code("001n") == "2"  # case-insensitive
    assert client.resolve_area_code("50C") == "36"


def test_resolve_area_code_returns_none_for_unknown_code(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(client, "_get", lambda *a, **k: _FakeResponse(text=_AREA_CODE_FORM_HTML))

    assert client.resolve_area_code("999Z") is None


def test_resolve_area_code_caches_across_calls(monkeypatch) -> None:
    client = _client()
    calls = []
    monkeypatch.setattr(client, "_get", lambda *a, **k: (calls.append(1), _FakeResponse(text=_AREA_CODE_FORM_HTML))[1])

    client.resolve_area_code("001N")
    client.resolve_area_code("50C")

    assert len(calls) == 1  # solo pidió el formulario una vez


def test_resolve_area_code_returns_none_on_request_error(monkeypatch) -> None:
    client = _client()

    def raise_error(*a, **k):
        raise requests.exceptions.ConnectionError("sin red")

    monkeypatch.setattr(client, "_get", raise_error)

    assert client.resolve_area_code("001N") is None
