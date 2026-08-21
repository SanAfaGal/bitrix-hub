from __future__ import annotations

import pytest

from app.forms.settings import load_form_link_secret


def test_load_form_link_secret_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("FORM_LINK_SECRET", "  un-secreto  ")

    assert load_form_link_secret() == "un-secreto"


def test_load_form_link_secret_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.forms.settings.load_dotenv", lambda: None)
    monkeypatch.delenv("FORM_LINK_SECRET", raising=False)

    with pytest.raises(RuntimeError):
        load_form_link_secret()
