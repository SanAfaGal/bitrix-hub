"""Pruebas de las reglas de negocio de process_deal_event, sin pasar por HTTP."""
from __future__ import annotations

from app.flows.registry_duplicate_check import check_matricula_in_xposure, process_deal_event
from app.xposure.models import PropertySearchResult
from tests.fakes import FakeCrmClient


class FakeXposureClient:
    # `results`: si se da una lista, cada llamada consume el siguiente
    # resultado en orden (para probar el reintento sin código de oficina);
    # si no, siempre devuelve `result`.
    def __init__(self, result: PropertySearchResult | None = None, results: list[PropertySearchResult] | None = None) -> None:
        self._result = result
        self._results = list(results) if results is not None else None
        self.calls: list[tuple[str, str | None]] = []
        self.called_with: str | None = None
        self.called_with_area_code: str | None = None

    def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None) -> PropertySearchResult:
        self.calls.append((tax_roll, tax_roll_area_code))
        self.called_with = tax_roll
        self.called_with_area_code = tax_roll_area_code
        if self._results is not None:
            return self._results.pop(0)
        return self._result


class FakeXposureClientDirect(FakeXposureClient):
    pass


def test_check_matricula_in_xposure_found_with_mls_is_duplicado() -> None:
    fake_xposure = FakeXposureClientDirect(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )

    is_duplicate, comment, url = check_matricula_in_xposure("50C-1945945", fake_xposure)

    assert is_duplicate is True
    assert comment == "Inmueble encontrado en Xposure. MLS: 999. Ver: https://example.com/999"
    assert url == "https://example.com/999"
    assert fake_xposure.called_with == "1945945"
    assert fake_xposure.called_with_area_code == "50C"


def test_check_matricula_in_xposure_not_found_is_not_duplicado() -> None:
    fake_xposure = FakeXposureClientDirect(
        PropertySearchResult(tax_roll="123456", exists=False, reason="No se encontraron resultados")
    )

    is_duplicate, comment, url = check_matricula_in_xposure("001-123456", fake_xposure)

    assert is_duplicate is False
    assert comment == "No se encontró el inmueble en Xposure para la matrícula 001-123456."
    assert url is None
    # Con código de oficina y sin código de oficina: ambos dieron "no existe".
    assert fake_xposure.calls == [("123456", "001"), ("123456", None)]


def test_check_matricula_in_xposure_retries_without_office_code_when_not_found() -> None:
    # El código de oficina de la matrícula del deal no coincide con el que
    # Xposure tiene guardado para ese folio (o no tiene ninguno) — la primera
    # búsqueda (con código) no encuentra nada, la segunda (solo el folio) sí.
    fake_xposure = FakeXposureClient(
        results=[
            PropertySearchResult(tax_roll="1134590", exists=False, reason="No se encontraron resultados"),
            PropertySearchResult(tax_roll="1134590", exists=True, mls="999", url="https://example.com/999"),
        ]
    )

    is_duplicate, comment, url = check_matricula_in_xposure("000-1134590", fake_xposure)

    assert is_duplicate is True
    assert comment == "Inmueble encontrado en Xposure. MLS: 999. Ver: https://example.com/999"
    assert url == "https://example.com/999"
    assert fake_xposure.calls == [("1134590", "000"), ("1134590", None)]


def test_check_matricula_in_xposure_found_without_mls_is_not_duplicado() -> None:
    fake_xposure = FakeXposureClientDirect(
        PropertySearchResult(tax_roll="123456", exists=True, reason="No se encontró MLS en la página")
    )

    is_duplicate, _, url = check_matricula_in_xposure("001-123456", fake_xposure)

    assert is_duplicate is False
    assert url is None


def test_check_matricula_in_xposure_without_office_code() -> None:
    fake_xposure = FakeXposureClientDirect(PropertySearchResult(tax_roll="1945945", exists=False))

    check_matricula_in_xposure("1945945", fake_xposure)

    assert fake_xposure.called_with == "1945945"
    assert fake_xposure.called_with_area_code is None


def test_process_deal_event_found_marks_duplicado() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "50C-1945945"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="50C-1945945", exists=True, mls="999", url="https://example.com/999")
    )

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "50C-1945945"}
    assert fake_xposure.called_with == "1945945"
    assert fake_xposure.called_with_area_code == "50C"
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
    assert fake_xposure.calls == [("123456", "001"), ("123456", None)]
    assert fake_crm.duplicado_updates == [("42", False)]
    assert fake_crm.pins == []  # solo se fija cuando hay duplicado


def test_process_deal_event_found_without_mls_does_not_pin() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "001-123456"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="001-123456", exists=True, reason="No se encontró MLS en la página")
    )

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "001-123456"}
    assert fake_xposure.called_with == "123456"
    assert fake_xposure.called_with_area_code == "001"
    assert fake_crm.duplicado_updates == [("42", False)]
    assert fake_crm.pins == []


def test_process_deal_event_found_marks_duplicado_sin_oficina() -> None:
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "1945945"}})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="1945945", exists=True, mls="999", url="https://example.com/999")
    )

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "1945945"}
    assert fake_xposure.called_with == "1945945"
    assert fake_xposure.called_with_area_code is None
    assert fake_crm.duplicado_updates == [("42", True)]


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
    fake_crm = FakeCrmClient(deals={"42": {"ID": "42", "MATRICULA": "ABC1234"}})
    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="", exists=False))

    result = process_deal_event("42", fake_crm, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "ABC1234"}
    assert fake_xposure.called_with is None
    assert fake_crm.duplicado_updates == []
    assert fake_crm.pins == []
    deal_id, comment = fake_crm.comments[0]
    assert deal_id == "42"
    assert "formato requerido" in comment
