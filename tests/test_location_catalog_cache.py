from __future__ import annotations

import pytest

from app.location_catalog import cache
from app.location_catalog.client import LocationSuggestion

_SAMPLE = [LocationSuggestion(sector_code="00081", display_label="PIEDECUESTA, Piedecuesta, Santander")]


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.reset_location_cache()
    yield
    cache.reset_location_cache()


def test_get_cached_locations_returns_freshly_fetched_data(monkeypatch) -> None:
    monkeypatch.setattr(cache, "fetch_all_locations", lambda: _SAMPLE)

    assert cache.get_cached_locations() == _SAMPLE


def test_get_cached_locations_does_not_refetch_within_ttl(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cache, "fetch_all_locations", lambda: calls.append(1) or _SAMPLE)

    cache.get_cached_locations()
    cache.get_cached_locations()

    assert len(calls) == 1


def test_get_cached_locations_keeps_stale_data_when_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr(cache, "fetch_all_locations", lambda: _SAMPLE)
    cache.get_cached_locations()

    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", -1)  # fuerza que el próximo get lo vea vencido
    monkeypatch.setattr(cache, "fetch_all_locations", lambda: [])

    assert cache.get_cached_locations() == _SAMPLE


def test_get_cached_locations_returns_empty_list_when_never_fetched_successfully(monkeypatch) -> None:
    monkeypatch.setattr(cache, "fetch_all_locations", lambda: [])

    assert cache.get_cached_locations() == []


def test_get_cached_locations_does_not_refetch_during_cooldown(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cache, "fetch_all_locations", lambda: calls.append(1) or [])

    cache.get_cached_locations()
    cache.get_cached_locations()

    assert len(calls) == 1
