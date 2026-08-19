"""Pruebas de las reglas de negocio de process_deal_event, sin pasar por HTTP."""
from __future__ import annotations

from app.bitrix.client import CRM_ENTITY_TYPE_DEAL
from app.flows.deal_duplicado import (
    FIELD_DUPLICADO,
    FIELD_MATRICULA,
    VALUE_DUPLICADO,
    VALUE_SIN_DUPLICADO,
    process_deal_event,
)
from app.xposure.models import PropertySearchResult


class FakeBitrixClient:
    def __init__(self, deal: dict) -> None:
        self._deal = deal
        self._next_comment_id = 1000
        self.comments: list[tuple[str, str, str]] = []
        self.updates: list[tuple[str, dict]] = []
        self.pins: list[tuple[int, int, str]] = []

    def get_deal(self, deal_id: str) -> dict:
        assert deal_id == "42"
        return self._deal

    def add_comment(self, entity_id: str, entity_type: str, comment: str) -> int:
        self.comments.append((entity_id, entity_type, comment))
        comment_id = self._next_comment_id
        self._next_comment_id += 1
        return comment_id

    def pin_comment(self, comment_id: int, owner_type_id: int, owner_id: str) -> None:
        self.pins.append((comment_id, owner_type_id, owner_id))

    def update_deal(self, deal_id: str, fields: dict) -> None:
        self.updates.append((deal_id, fields))


class FakeXposureClient:
    def __init__(self, result: PropertySearchResult) -> None:
        self._result = result
        self.called_with: str | None = None

    def search_property(self, tax_roll: str) -> PropertySearchResult:
        self.called_with = tax_roll
        return self._result


def test_process_deal_event_found_marks_duplicado() -> None:
    fake_bitrix = FakeBitrixClient({"ID": "42", FIELD_MATRICULA: "5322493"})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="5322493", exists=True, mls="999", url="https://example.com/999")
    )

    result = process_deal_event("42", fake_bitrix, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "5322493"}
    assert fake_xposure.called_with == "5322493"
    assert fake_bitrix.comments == [
        ("42", "deal", "Inmueble encontrado en Xposure. MLS: 999. Ver: https://example.com/999")
    ]
    assert fake_bitrix.updates == [("42", {FIELD_DUPLICADO: VALUE_DUPLICADO})]
    assert fake_bitrix.pins == [(1000, CRM_ENTITY_TYPE_DEAL, "42")]


def test_process_deal_event_not_found_marks_sin_duplicado() -> None:
    fake_bitrix = FakeBitrixClient({"ID": "42", FIELD_MATRICULA: "5322493"})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="5322493", exists=False, reason="No se encontraron resultados")
    )

    result = process_deal_event("42", fake_bitrix, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "5322493"}
    assert fake_bitrix.updates == [("42", {FIELD_DUPLICADO: VALUE_SIN_DUPLICADO})]
    assert fake_bitrix.pins == []  # solo se fija cuando hay duplicado


def test_process_deal_event_found_without_mls_does_not_pin() -> None:
    fake_bitrix = FakeBitrixClient({"ID": "42", FIELD_MATRICULA: "5322493"})
    fake_xposure = FakeXposureClient(
        PropertySearchResult(tax_roll="5322493", exists=True, reason="No se encontró MLS en la página")
    )

    result = process_deal_event("42", fake_bitrix, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": "5322493"}
    assert fake_bitrix.updates == [("42", {FIELD_DUPLICADO: VALUE_SIN_DUPLICADO})]
    assert fake_bitrix.pins == []


def test_process_deal_event_without_matricula_skips_xposure() -> None:
    fake_bitrix = FakeBitrixClient({"ID": "42"})
    fake_xposure = FakeXposureClient(PropertySearchResult(tax_roll="", exists=False))

    result = process_deal_event("42", fake_bitrix, lambda: fake_xposure)

    assert result == {"ok": True, "deal_id": "42", "matricula": None}
    assert fake_xposure.called_with is None
    assert fake_bitrix.updates == [("42", {FIELD_DUPLICADO: VALUE_SIN_DUPLICADO})]
    assert fake_bitrix.pins == []  # sin matrícula: comentario, pero sin fijar
