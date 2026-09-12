from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin import router as admin_router
from app.auth.deps import require_admin, require_staff_user
from app.location_catalog.client import Sector
from app.main import app
from app.message_templates import db as templates_db
from app.message_templates.models import Base

_ADMIN_EMAIL = "admin@albertoalvarez.com"
_ADMIN_NAME = "Ana Admin"

_SECTORS = [
    Sector(sector_code="001", sector="Centro", zona="Zona 1", ciudad="Bogotá", departamento="Cundinamarca", pais="Colombia", cobertura=True),
    Sector(sector_code="002", sector="Norte", zona="Zona 2", ciudad="Cali", departamento="Valle", pais="Colombia", cobertura=False),
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(templates_db, "SessionLocal", sessionmaker(bind=engine, future=True))
    monkeypatch.setattr(admin_router.location_catalog_client, "fetch_all_sectores", lambda: list(_SECTORS))
    return TestClient(app)


def _log_in(client: TestClient) -> None:
    app.dependency_overrides[require_admin] = lambda: _ADMIN_EMAIL
    app.dependency_overrides[require_staff_user] = lambda: {"name": _ADMIN_NAME, "email": _ADMIN_EMAIL}


def test_coverage_static_css_and_js_are_reachable(client: TestClient) -> None:
    css = client.get("/static/admin/coverage.css")
    js = client.get("/static/admin/coverage.js")

    assert css.status_code == 200
    assert js.status_code == 200


@pytest.fixture(autouse=True)
def _clear_override():
    yield
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_staff_user, None)


def test_coverage_page_requires_login(client: TestClient) -> None:
    response = client.get("/admin/cobertura", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login?next=/admin/cobertura"


def test_coverage_page_lists_all_sectors_by_default(client: TestClient) -> None:
    _log_in(client)

    response = client.get("/admin/cobertura")

    assert response.status_code == 200
    assert "Centro" in response.text
    assert "Norte" in response.text


def test_coverage_page_renders_cascade_filters_and_row_data_attrs(client: TestClient) -> None:
    _log_in(client)

    response = client.get("/admin/cobertura")

    assert response.status_code == 200
    for level in ("pais", "departamento", "ciudad", "zona", "sector"):
        assert f'data-coverage-cascade="{level}"' in response.text
    assert 'data-pais="Colombia"' in response.text
    assert 'data-ciudad="Bogotá"' in response.text
    assert 'data-coverage-visible-count' in response.text
    assert 'data-coverage-selected-count' in response.text
    assert 'data-coverage-clear' in response.text
    # El select de estado no debe ir en un <form> propio anidado dentro del
    # form de batch (HTML inválido, ver coverage_page.py::_estado_select_html) —
    # el único <form method="get"...> del shell es el de logout, que no aplica acá.
    assert '<form method="get"' not in response.text


def test_coverage_page_shows_error_flash_when_dwh_is_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin_router.location_catalog_client, "fetch_all_sectores", lambda: None)
    _log_in(client)

    response = client.get("/admin/cobertura")

    assert response.status_code == 200
    assert "No se pudo leer el catálogo de sectores del DWH de Mobilia." in response.text


def test_coverage_page_filters_by_estado(client: TestClient) -> None:
    _log_in(client)

    response = client.get("/admin/cobertura", params={"estado": "con_cobertura"})

    assert response.status_code == 200
    assert "Centro" in response.text
    assert "Norte" not in response.text


def test_batch_activates_selected_sectors(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in(client)
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        admin_router.location_catalog_client,
        "set_cobertura",
        lambda codes, covered: calls.append((codes, covered)) or True,
    )

    response = client.post(
        "/admin/cobertura/batch",
        data={"accion": "activar", "estado": "sin_cobertura", "sector_code": ["002"]},
    )

    assert response.status_code == 200
    assert "Activada la cobertura de 1 sector(es)." in response.text
    assert calls == [(["002"], True)]


def test_batch_deactivates_selected_sectors(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in(client)
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        admin_router.location_catalog_client,
        "set_cobertura",
        lambda codes, covered: calls.append((codes, covered)) or True,
    )

    response = client.post(
        "/admin/cobertura/batch",
        data={"accion": "desactivar", "estado": "todos", "sector_code": ["001"]},
    )

    assert response.status_code == 200
    assert "Desactivada la cobertura de 1 sector(es)." in response.text
    assert calls == [(["001"], False)]


def test_batch_with_no_selection_does_not_call_set_cobertura(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in(client)
    monkeypatch.setattr(
        admin_router.location_catalog_client,
        "set_cobertura",
        lambda *a, **k: pytest.fail("no debería llamarse sin selección"),
    )

    response = client.post("/admin/cobertura/batch", data={"accion": "activar", "estado": "todos"})

    assert response.status_code == 200
    assert "No seleccionaste ningún sector." in response.text


def test_batch_rejects_invalid_accion(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in(client)
    monkeypatch.setattr(
        admin_router.location_catalog_client,
        "set_cobertura",
        lambda *a, **k: pytest.fail("no debería llamarse con acción inválida"),
    )

    response = client.post(
        "/admin/cobertura/batch", data={"accion": "borrar-todo", "estado": "todos", "sector_code": ["001"]}
    )

    assert response.status_code == 200
    assert "Acción inválida." in response.text


def test_batch_shows_error_flash_when_update_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _log_in(client)
    monkeypatch.setattr(admin_router.location_catalog_client, "set_cobertura", lambda codes, covered: False)

    response = client.post(
        "/admin/cobertura/batch", data={"accion": "activar", "estado": "todos", "sector_code": ["001"]}
    )

    assert response.status_code == 200
    assert "No se pudo actualizar la cobertura en el DWH" in response.text
