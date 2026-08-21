from __future__ import annotations

import pytest

from app.crm.deps import get_crm_client


def test_get_crm_client_returns_bitrix_client_for_bitrix_provider(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr("app.crm.deps.load_crm_settings", lambda: "bitrix")
    monkeypatch.setattr("app.crm.deps.get_bitrix_client", lambda: sentinel)

    assert get_crm_client() is sentinel


def test_get_crm_client_raises_for_unknown_provider(monkeypatch) -> None:
    monkeypatch.setattr("app.crm.deps.load_crm_settings", lambda: "salesforce")

    with pytest.raises(RuntimeError, match="salesforce"):
        get_crm_client()
