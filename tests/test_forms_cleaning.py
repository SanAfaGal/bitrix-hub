from __future__ import annotations

from app.forms.cleaning import slugify_filename


def test_slugify_filename_strips_accents_and_replaces_spaces() -> None:
    assert slugify_filename("Cra 15 #93-47, Bogotá") == "Cra-15-93-47-Bogota"


def test_slugify_filename_collapses_repeated_separators() -> None:
    assert slugify_filename("  Calle   10 ## 20 -- 30  ") == "Calle-10-20-30"


def test_slugify_filename_truncates_to_max_length() -> None:
    result = slugify_filename("a" * 100, max_length=10)
    assert result == "a" * 10


def test_slugify_filename_trims_trailing_separator_after_truncation() -> None:
    result = slugify_filename("abcde-fghij-klmno", max_length=6)
    assert result == "abcde"
