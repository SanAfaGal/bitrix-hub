"""Pruebas del chequeo de cobertura por ubicación (placeholder, ver app/forms/coverage.py)."""
from __future__ import annotations

from app.forms.coverage import is_location_covered


def test_is_location_covered_always_true_while_listing_is_pending():
    assert is_location_covered("El Poblado, Medellín, Antioquia") is True


def test_is_location_covered_true_even_for_empty_location():
    assert is_location_covered("") is True
