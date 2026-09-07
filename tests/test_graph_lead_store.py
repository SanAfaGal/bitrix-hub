from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.flows import graph_lead_store as store
from app.flows.whatsapp_bot_models import Base, Conversation


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


def test_is_processed_false_when_no_row(session) -> None:
    assert store.is_processed("track-1", session=session) is False


def test_mark_processed_then_is_processed_true(session) -> None:
    store.mark_processed("track-1", status="created", deal_id="123", session=session)

    assert store.is_processed("track-1", session=session) is True


def test_mark_processed_sets_channel_and_email_tracking_id(session) -> None:
    store.mark_processed("track-1", status="created", deal_id="123", name="Diana", phone="573001112233", session=session)

    row = session.query(Conversation).filter_by(email_tracking_id="track-1").one()
    assert row.channel == "email"
    assert row.chat_id is None
    assert row.name == "Diana"
    assert row.phone == "573001112233"
    assert row.deal_id == "123"


def test_mark_processed_twice_updates_same_row(session) -> None:
    store.mark_processed("track-1", status="error", detail="sin_telefono", session=session)
    store.mark_processed("track-1", status="created", deal_id="123", session=session)

    row = session.query(Conversation).filter_by(email_tracking_id="track-1").one()
    assert row.status == "created"
    assert row.deal_id == "123"


def test_get_processed_returns_none_when_no_row(session) -> None:
    assert store.get_processed("track-1", session=session) is None


def test_get_processed_returns_saved_fields(session) -> None:
    store.mark_processed("track-1", status="skipped", detail="service_type=comprar", session=session)

    result = store.get_processed("track-1", session=session)

    assert result["status"] == "skipped"
    assert result["detail"] == "service_type=comprar"
    assert result["deal_id"] is None
