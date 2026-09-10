from __future__ import annotations

from app.flows import whatsapp_bot_conversation_store as store_module
from app.flows.whatsapp_bot import ConversationStore


def test_last_message_time_is_purged_after_ttl_expires(monkeypatch) -> None:
    """Sin esto, `_last_message_time` crece sin límite: un timestamp por cada chat
    distinto que haya escrito alguna vez, nunca liberado."""
    store = ConversationStore()
    fake_now = [1000.0]
    monkeypatch.setattr(store_module.time, "monotonic", lambda: fake_now[0])

    store.mark_message_received("111@c.us")
    assert "111@c.us" in store._last_message_time

    fake_now[0] += store_module.LAST_MESSAGE_TIME_TTL_SECONDS + 1
    store.is_rate_limited("222@c.us")  # cualquier llamada dispara la purga

    assert "111@c.us" not in store._last_message_time


def test_get_full_history_returns_all_turns_in_order() -> None:
    store = ConversationStore(max_history_turns=6)
    store.add_turn("573001112233@c.us", "user", "hola")
    store.add_turn("573001112233@c.us", "assistant", "hola, en qué te ayudo")
    store.add_turn("573001112233@c.us", "user", "quiero vender un apto")

    history = store.get_full_history("573001112233@c.us")

    assert [m["content"] for m in history] == ["hola", "hola, en qué te ayudo", "quiero vender un apto"]
    assert all("created_at" in m for m in history)


def test_add_turn_uses_given_created_at_instead_of_current_time() -> None:
    """Permite pasar el `timestamp` real de Waha (ej. en el backfill de historial,
    `whatsapp_bot_history_seed.py`) en vez de siempre grabar el momento del insert."""
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola", created_at=12345.0)

    history = store.get_full_history("573001112233@c.us")

    assert history[0]["created_at"] == 12345.0


def test_get_full_history_is_never_trimmed_while_get_history_caps_to_llm_context() -> None:
    """`add_turn` ya no borra nada de la base — `get_full_history` (auditoría, panel admin)
    siempre muestra todo. El recorte a `max_history_turns*2` es solo de lectura, para lo que
    se le manda al LLM como contexto (`get_history`), ver `whatsapp_bot_store.py::add_turn`."""
    store = ConversationStore(max_history_turns=1)
    for i in range(5):
        store.add_turn("573001112233@c.us", "user", f"mensaje {i}")

    assert len(store.get_full_history("573001112233@c.us")) == 5
    assert len(store.get_history("573001112233@c.us")) == 2


def test_history_seeded_defaults_to_false_and_can_be_set() -> None:
    store = ConversationStore()

    assert store.get_history_seeded("573001112233@c.us") is False

    store.set_history_seeded("573001112233@c.us")

    assert store.get_history_seeded("573001112233@c.us") is True


def test_zone_asked_defaults_to_false_and_can_be_set() -> None:
    store = ConversationStore()

    assert store.get_zone_asked("573001112233@c.us") is False

    store.set_zone_asked("573001112233@c.us")

    assert store.get_zone_asked("573001112233@c.us") is True


def test_zone_in_coverage_defaults_to_none_and_can_be_set_true_or_false() -> None:
    store = ConversationStore()

    assert store.get_zone_in_coverage("573001112233@c.us") is None

    store.set_zone_in_coverage("573001112233@c.us", True)
    assert store.get_zone_in_coverage("573001112233@c.us") is True

    store.set_zone_in_coverage("573001112233@c.us", False)
    assert store.get_zone_in_coverage("573001112233@c.us") is False


def test_has_assistant_turn_false_for_user_only_history() -> None:
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola")

    assert store.has_assistant_turn("573001112233@c.us") is False

    store.add_turn("573001112233@c.us", "assistant", "hola! en qué te ayudo")

    assert store.has_assistant_turn("573001112233@c.us") is True


def test_has_assistant_turn_false_for_unknown_chat() -> None:
    store = ConversationStore()

    assert store.has_assistant_turn("573001112233@c.us") is False


def test_clear_messages_removes_turns_but_keeps_lead_row() -> None:
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola")
    store.add_turn("573001112233@c.us", "assistant", "hola! en qué te ayudo")
    store.set_deal_id("573001112233@c.us", "42")

    store.clear_messages("573001112233@c.us")

    assert store.get_full_history("573001112233@c.us") == []
    # La fila de lead (deal_id, identidad, etc.) no se toca.
    assert store.get_deal_id("573001112233@c.us") == "42"


def test_list_chats_empty_store() -> None:
    store = ConversationStore()
    assert store.list_chats() == []


def test_list_chats_returns_summary_ordered_by_last_message() -> None:
    store = ConversationStore()
    store.add_turn("111@c.us", "user", "primero")
    store.add_turn("222@c.us", "user", "segundo")
    store.add_turn("222@c.us", "assistant", "tercero, el más reciente")
    store.set_deal_id("222@c.us", "42")
    store.set_confirmed_identity("222@c.us", "Ana", "573001112233")

    chats = store.list_chats()

    assert [c["chat_id"] for c in chats] == ["222@c.us", "111@c.us"]
    top = chats[0]
    assert top["last_content"] == "tercero, el más reciente"
    assert top["message_count"] == 2
    assert top["deal_id"] == "42"
    assert top["confirmed_name"] == "Ana"
    assert top["confirmed_phone"] == "573001112233"

    bottom = chats[1]
    assert bottom["deal_id"] is None
    assert bottom["confirmed_name"] is None
