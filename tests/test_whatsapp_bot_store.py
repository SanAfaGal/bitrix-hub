from __future__ import annotations

from app.flows.whatsapp_bot import ConversationStore


def test_get_full_history_returns_all_turns_in_order() -> None:
    store = ConversationStore(max_history_turns=6)
    store.add_turn("573001112233@c.us", "user", "hola")
    store.add_turn("573001112233@c.us", "assistant", "hola, en qué te ayudo")
    store.add_turn("573001112233@c.us", "user", "quiero vender un apto")

    history = store.get_full_history("573001112233@c.us")

    assert [m["content"] for m in history] == ["hola", "hola, en qué te ayudo", "quiero vender un apto"]
    assert all("created_at" in m for m in history)


def test_get_full_history_has_no_read_time_limit() -> None:
    """`get_full_history` no aplica un LIMIT propio en la lectura — muestra todo lo que
    `add_turn` haya dejado en la tabla (el recorte a `max_history_turns*2` ocurre al
    escribir, no al leer; ver `add_turn`)."""
    store = ConversationStore(max_history_turns=1)
    for i in range(5):
        store.add_turn("573001112233@c.us", "user", f"mensaje {i}")

    assert len(store.get_full_history("573001112233@c.us")) == len(store.get_history("573001112233@c.us")) == 2


def test_list_chats_empty_store() -> None:
    store = ConversationStore()
    assert store.list_chats() == []


def test_list_chats_returns_summary_ordered_by_last_message() -> None:
    store = ConversationStore()
    store.add_turn("111@c.us", "user", "primero")
    store.add_turn("222@c.us", "user", "segundo")
    store.add_turn("222@c.us", "assistant", "tercero, el más reciente")
    store.set_deal_id("222@c.us", "42")
    store.set_confirmed_name("222@c.us", "Ana")
    store.set_confirmed_phone("222@c.us", "573001112233")

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
