from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.graph import store
from app.graph.models import Base, ProcessedGraphMessage


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
    assert store.is_processed("msg-1", session=session) is False


def test_mark_processed_then_is_processed_true(session) -> None:
    store.mark_processed("msg-1", status="created", deal_id="123", session=session)

    assert store.is_processed("msg-1", session=session) is True


def test_mark_processed_twice_updates_same_row(session) -> None:
    store.mark_processed("msg-1", status="error", detail="sin_telefono", session=session)
    store.mark_processed("msg-1", status="created", deal_id="123", session=session)

    row = session.get(ProcessedGraphMessage, "msg-1")
    assert row.status == "created"
    assert row.deal_id == "123"
