from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.message_templates import store
from app.message_templates.models import Base


@pytest.fixture
def session():
    """Sesión sobre una base SQLite en memoria — la tabla no usa nada específico de MySQL."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_get_template_falls_back_to_default_when_no_row(session) -> None:
    assert store.get_template("whatsapp_welcome_unknown", session=session) == store.DEFAULT_TEMPLATES[
        "whatsapp_welcome_unknown"
    ]


def test_set_template_then_get_returns_saved_content(session) -> None:
    store.set_template("whatsapp_welcome_unknown", "Hola, texto nuevo", updated_by="andrea", session=session)

    assert store.get_template("whatsapp_welcome_unknown", session=session) == "Hola, texto nuevo"


def test_set_template_updates_existing_row(session) -> None:
    store.set_template("whatsapp_welcome_unknown", "primero", updated_by="andrea", session=session)
    store.set_template("whatsapp_welcome_unknown", "segundo", updated_by="andrea", session=session)

    assert store.get_template("whatsapp_welcome_unknown", session=session) == "segundo"


def test_set_template_rejects_unknown_key(session) -> None:
    with pytest.raises(ValueError):
        store.set_template("no_existe", "texto", updated_by="andrea", session=session)


def test_render_template_replaces_variables(session) -> None:
    store.set_template("whatsapp_welcome_known", "Hola {{nombre}}, bienvenido", updated_by="andrea", session=session)

    result = store.render_template("whatsapp_welcome_known", session=session, nombre="Juan")

    assert result == "Hola Juan, bienvenido"


def test_render_template_falls_back_to_default_with_variables(session) -> None:
    result = store.render_template("bitrix_authorization_link_message", session=session, link="https://x.com/y")

    assert "https://x.com/y" in result


def test_list_templates_includes_all_known_keys_with_defaults(session) -> None:
    store.set_template("whatsapp_welcome_unknown", "editado", updated_by="andrea", session=session)

    result = store.list_templates(session=session)

    assert result.keys() == store.DEFAULT_TEMPLATES.keys()
    assert result["whatsapp_welcome_unknown"] == "editado"
    assert result["whatsapp_system_prompt"] == store.DEFAULT_TEMPLATES["whatsapp_system_prompt"]


def test_seed_defaults_inserts_missing_keys_without_overwriting_existing(session) -> None:
    store.set_template("whatsapp_welcome_unknown", "ya editado", updated_by="andrea", session=session)

    store.seed_defaults(session=session)

    result = store.list_templates(session=session)
    assert result["whatsapp_welcome_unknown"] == "ya editado"
    assert result["whatsapp_system_prompt"] == store.DEFAULT_TEMPLATES["whatsapp_system_prompt"]


def test_get_template_falls_back_to_default_when_db_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin `session=`, usa `db.SessionLocal` real — si MySQL no está disponible, no debe lanzar."""
    assert store.get_template("whatsapp_transcription_failed") == store.DEFAULT_TEMPLATES[
        "whatsapp_transcription_failed"
    ]
