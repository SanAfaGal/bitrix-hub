"""Pruebas del chequeo de cobertura por ubicación (ver app/forms/coverage.py)."""
from __future__ import annotations

import app.forms.coverage as coverage_module
from app.forms.coverage import check_coverage, is_location_covered


def test_is_location_covered_true_when_sector_has_coverage(monkeypatch) -> None:
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: True)

    assert is_location_covered("00081") is True


def test_is_location_covered_false_when_sector_has_no_coverage(monkeypatch) -> None:
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: False)

    assert is_location_covered("00081") is False


def test_is_location_covered_true_when_coverage_cannot_be_determined(monkeypatch) -> None:
    # DWH caído o sector_code no reconocido: se deja pasar al cliente en vez
    # de bloquearlo por un problema técnico nuestro (decisión de negocio).
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: None)

    assert is_location_covered("00081") is True


def test_is_location_covered_false_for_missing_sector_code() -> None:
    assert is_location_covered(None) is False
    assert is_location_covered("") is False


def test_check_coverage_passes_when_covered(monkeypatch) -> None:
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: True)

    result = check_coverage("00081", is_internal=False)

    assert result.covered is True
    assert result.blocked is False
    assert result.used_exception is False


def test_check_coverage_public_blocks_without_override_option(monkeypatch) -> None:
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: False)

    result = check_coverage("00081", is_internal=False, override=True)  # override se ignora para público

    assert result.blocked is True
    assert result.used_exception is False


def test_check_coverage_internal_blocks_without_override(monkeypatch) -> None:
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: False)

    result = check_coverage("00081", is_internal=True)

    assert result.blocked is True
    assert result.used_exception is False
    assert result.message is not None


def test_check_coverage_internal_passes_with_override(monkeypatch) -> None:
    monkeypatch.setattr(coverage_module, "get_sector_coverage", lambda sector_code: False)

    result = check_coverage("00081", is_internal=True, override=True)

    assert result.blocked is False
    assert result.used_exception is True
