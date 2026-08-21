from __future__ import annotations

import pytest

from app.crm.settings import load_crm_settings


def test_load_crm_settings_reads_and_normalizes_env_var(monkeypatch) -> None:
    monkeypatch.setenv("CRM_PROVIDER", " Bitrix ")

    assert load_crm_settings() == "bitrix"


def test_load_crm_settings_raises_when_missing(monkeypatch) -> None:
    # No basta con delenv: load_dotenv() volvería a leerla del .env real del
    # repo si está seteada ahí. Se anula para probar la ausencia de verdad.
    monkeypatch.setattr("app.crm.settings.load_dotenv", lambda: None)
    monkeypatch.delenv("CRM_PROVIDER", raising=False)

    with pytest.raises(RuntimeError):
        load_crm_settings()
