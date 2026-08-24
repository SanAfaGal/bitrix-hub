"""Pruebas de las reglas de negocio de process_deal_event, sin pasar por HTTP."""
from __future__ import annotations

from app.flows.deal_duplicado import process_deal_event
from app.xposure.models import PropertySearchResult
from tests.fakes import FakeCrmClient


class FakeXposureClient:
    def __init__(self, result: PropertySearchResult) -> None:
        self._result = result
        self.called_with: str | None = None

    def search_property(self, tax_roll: str) -> PropertySearchResult:
        self.called_with = tax_roll
        return self._result


def test_process_deal_event_found_marks_duplicado() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "50C-1945945"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="50C-1945945", exists=True, mls="999", url="https://example.com/999")
    )

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "50C-1945945"}
    assert fake_xposure.called_with == "50C-1945945"
    assert fake_crm.comments == [
        ("42", "Inmueble encontrado en Xposure. MLS: 999. Ver: https://example.com/999")
    ]
    assert fake_crm.duplicado_updates == [("42", True)]
    assert fake_crm.pins == [(1000, "42")]


def test_process_deal_event_not_found_marks_sin_duplicado() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "001-123456"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="001-123456", exists=False, reason="No se encontraron resultados")
    )

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "001-123456"}
    assert fake_crm.duplicado_updates == [("42", False)]
    assert fake_crm.pins == []  # solo se fija cuando hay duplicado


def test_process_deal_event_found_without_mls_does_not_pin() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "001-123456"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="001-123456", exists=True, reason="No se encontró MLS en la página")
    )

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "001-123456"}
    assert fake_crm.duplicado_updates == [("42", False)]
    assert fake_crm.pins == []


def test_process_deal_event_without_matricula_skips_xposure() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42"}})
    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="", exists=False))

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": None}
    assert fake_xposure.called_with is None
    # Sin matrícula no se pudo validar nada: solo queda el comentario, el
    # campo Duplicado/Sin duplicado (V_Validación MLS) no se toca.
    assert fake_crm.duplicado_updates == []
    assert fake_crm.pins == []


def test_process_deal_event_with_invalid_matricula_format_skips_xposure() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "5322493"}})
    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="", exists=False))

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "5322493"}
    assert fake_xposure.called_with is None
    assert fake_crm.duplicado_updates == []
    assert fake_crm.pins == []
    deal_id, comment = fake_crm.comments[0]
    assert deal_id == "42"
    assert "formato requerido" in comment
