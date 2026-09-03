"""Pruebas del chequeo en vivo de matrícula usado por el wizard del formulario
de Autorización de Corretaje (app/flows/registry_live_check.py)."""
from __future__ import annotations

from app.flows.registry_live_check import check_registration_number_live
from app.xposure.models import PropertySearchResult
from tests.fakes import FakeCrmClient


class FakeXposureClient:
    def __init__(self, result: PropertySearchResult) -> None:
        self._result = result

    def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None) -> PropertySearchResult:
        return self._result


def test_check_registration_number_live_found_blocks_without_crm() -> None:
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )

    result = check_registration_number_live("50C-1945945", lambda: fake_xposure)

    assert result["duplicate"] is True
    assert result["message"] != ""


def test_check_registration_number_live_not_found_does_not_block() -> None:
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="123456", exists=False, reason="No se encontraron resultados")
    )

    result = check_registration_number_live("001-123456", lambda: fake_xposure)

    assert result["duplicate"] is False
    assert result["message"] == ""


def test_check_registration_number_live_records_duplicate_on_deal_when_given() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )

    result = check_registration_number_live(
        "50C-1945945", lambda: fake_xposure, crm_client=fake_crm, deal_id="42"
    )

    assert result["duplicate"] is True
    assert fake_crm.duplicado_updates == [("42", True)]
    assert fake_crm.pins == [(1000, "42")]
    assert len(fake_crm.comments) == 1


def test_check_registration_number_live_does_not_pin_when_not_duplicate() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="123456", exists=False, reason="No se encontraron resultados")
    )

    result = check_registration_number_live(
        "001-123456", lambda: fake_xposure, crm_client=fake_crm, deal_id="42"
    )

    assert result["duplicate"] is False
    assert fake_crm.duplicado_updates == [("42", False)]
    assert fake_crm.pins == []


def test_check_registration_number_live_without_deal_id_does_not_touch_crm() -> None:
    fake_crm = FakeCrmClient()
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )

    check_registration_number_live("50C-1945945", lambda: fake_xposure, crm_client=fake_crm, deal_id=None)

    assert fake_crm.duplicado_updates == []
    assert fake_crm.comments == []
