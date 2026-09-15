from __future__ import annotations

from app.flows.whatsapp_bot import ConversationStore


def test_has_reached_false_before_any_mark() -> None:
    store = ConversationStore()

    assert store.has_reached("573001112233@c.us", "zone_coverage") is False


def test_mark_reached_without_value_makes_has_reached_true() -> None:
    store = ConversationStore()
    chat_id = "573001112233@c.us"

    store.mark_reached(chat_id, "zone_coverage")

    assert store.has_reached(chat_id, "zone_coverage") is True
    assert store.get_answer(chat_id, "zone_coverage") is None


def test_get_answer_none_when_row_absent() -> None:
    store = ConversationStore()

    assert store.get_answer("573001112233@c.us", "zone_coverage") is None


def test_get_answer_returns_bool_value_once_set() -> None:
    store = ConversationStore()
    chat_id = "573001112233@c.us"

    store.mark_reached(chat_id, "zone_coverage", value=True)
    assert store.get_answer(chat_id, "zone_coverage") is True

    store.mark_reached(chat_id, "zone_coverage", value=False)
    assert store.get_answer(chat_id, "zone_coverage") is False


def test_mark_reached_sets_reached_at_only_on_first_call() -> None:
    """Segunda llamada sobre el mismo checkpoint (ej. de 'asked' a 'answered') actualiza
    `value` pero no debe pisar el `reached_at` original."""
    from app.flows import whatsapp_bot_checkpoints as checkpoints_db
    from app.flows import whatsapp_bot_db as store_engine
    from app.flows.whatsapp_bot_models import LeadCheckpoint
    from sqlalchemy.orm import Session

    engine = store_engine.build_sqlite_engine()
    with Session(engine) as session:
        checkpoints_db.mark_reached(session, "573001112233@c.us", "zone_coverage")
        checkpoint = checkpoints_db._get_checkpoint_by_key(session, "zone_coverage")
        lead = checkpoints_db._get_by_chat_id(session, "573001112233@c.us")
        first_reached_at = (
            session.query(LeadCheckpoint)
            .filter(LeadCheckpoint.lead_id == lead.id, LeadCheckpoint.checkpoint_id == checkpoint.id)
            .one()
            .reached_at
        )

        checkpoints_db.mark_reached(session, "573001112233@c.us", "zone_coverage", value=True)
        second_reached_at = (
            session.query(LeadCheckpoint)
            .filter(LeadCheckpoint.lead_id == lead.id, LeadCheckpoint.checkpoint_id == checkpoint.id)
            .one()
            .reached_at
        )

    assert first_reached_at == second_reached_at


def test_get_next_checkpoint_respects_order_and_skips_reached() -> None:
    store = ConversationStore()
    chat_id = "573001112233@c.us"

    first = store.get_next_checkpoint(chat_id)
    assert first.key == "zone_coverage"

    store.mark_reached(chat_id, "zone_coverage", value=True)

    second = store.get_next_checkpoint(chat_id)
    assert second.key == "explanation"

    store.mark_reached(chat_id, "explanation")
    store.mark_reached(chat_id, "authorization_link")

    assert store.get_next_checkpoint(chat_id) is None


def test_get_next_checkpoint_excludes_inactive_checkpoints() -> None:
    from app.flows import whatsapp_bot_db as store_engine
    from app.flows.whatsapp_bot_models import Checkpoint
    from sqlalchemy.orm import Session

    engine = store_engine.build_sqlite_engine()
    with Session(engine) as session:
        zone = session.query(Checkpoint).filter(Checkpoint.key == "zone_coverage").one()
        zone.active = False
        session.commit()

    store = ConversationStore(engine=engine)
    chat_id = "573001112233@c.us"

    first = store.get_next_checkpoint(chat_id)

    assert first.key == "explanation"
