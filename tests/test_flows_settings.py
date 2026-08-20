from __future__ import annotations

import pytest

from app.flows.settings import load_public_base_url


def test_load_public_base_url_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("HUB_PUBLIC_BASE_URL", "https://hub.example.com/")

    assert load_public_base_url() == "https://hub.example.com"


def test_load_public_base_url_raises_when_missing(monkeypatch) -> None:
    # No basta con delenv: load_dotenv() volvería a leerla del .env real del
    # repo si está seteada ahí. Se anula para probar la ausencia de verdad.
    monkeypatch.setattr("app.flows.settings.load_dotenv", lambda: None)
    monkeypatch.delenv("HUB_PUBLIC_BASE_URL", raising=False)

    with pytest.raises(RuntimeError):
        load_public_base_url()
