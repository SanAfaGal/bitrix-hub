from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.xposure.deps import get_xposure_client
from app.xposure.models import PropertySearchResult

client = TestClient(app)


class _FakeClient:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self._fail_on = fail_on or set()

    def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None) -> PropertySearchResult:
        if tax_roll in self._fail_on:
            raise RuntimeError(f"fallo de red para {tax_roll}")
        return PropertySearchResult(tax_roll=tax_roll, exists=True, mls=f"mls-{tax_roll}")


def test_bulk_returns_a_result_per_tax_roll_in_order() -> None:
    app.dependency_overrides[get_xposure_client] = lambda: _FakeClient()
    try:
        response = client.post("/properties/bulk", json={"tax_rolls": ["1", "2", "3"]})
    finally:
        app.dependency_overrides.pop(get_xposure_client, None)

    assert response.status_code == 200
    body = response.json()
    assert [item["tax_roll"] for item in body] == ["1", "2", "3"]
    assert all(item["exists"] for item in body)


def test_bulk_does_not_abort_the_whole_batch_when_one_tax_roll_fails() -> None:
    app.dependency_overrides[get_xposure_client] = lambda: _FakeClient(fail_on={"2"})
    try:
        response = client.post("/properties/bulk", json={"tax_rolls": ["1", "2", "3"]})
    finally:
        app.dependency_overrides.pop(get_xposure_client, None)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["exists"] is True
    assert body[1]["exists"] is False
    assert "fallo de red para 2" in body[1]["reason"]
    assert body[2]["exists"] is True


def test_bulk_rejects_more_than_the_maximum_allowed_tax_rolls() -> None:
    response = client.post("/properties/bulk", json={"tax_rolls": [str(i) for i in range(51)]})

    assert response.status_code == 422


def test_bulk_rejects_empty_list() -> None:
    response = client.post("/properties/bulk", json={"tax_rolls": []})

    assert response.status_code == 422
