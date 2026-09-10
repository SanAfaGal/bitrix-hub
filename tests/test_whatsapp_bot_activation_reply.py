from __future__ import annotations

import json

from app.flows.whatsapp_bot import BotConfig, ConversationStore, reply_after_activation
from tests.fakes import FakeCrmClient


class FakeWahaClient:
    def __init__(self, send_result: bool = True) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.send_result


class FakeLlmClient:
    def __init__(self, reply_text: str | None = "seguimos aca, contame que necesitas") -> None:
        self.reply_text = reply_text
        self.calls: list[tuple[str, list[dict], str]] = []

    def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
        self.calls.append((system_prompt, history, user_text))
        if self.reply_text is None:
            return None
        return json.dumps({"reply": self.reply_text, "fields": {}})


def _enabled_config() -> BotConfig:
    return BotConfig(enabled=True, max_history_turns=6)


def test_reply_after_activation_returns_none_when_no_history() -> None:
    store = ConversationStore()
    waha = FakeWahaClient()
    llm = FakeLlmClient()

    result = reply_after_activation(
        "573001112233@c.us", waha, llm, FakeCrmClient(), config=_enabled_config(), store=store
    )

    assert result is None
    assert waha.calls == []


def test_reply_after_activation_returns_none_when_last_turn_is_assistant() -> None:
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.add_turn(chat_id, "user", "hola")
    store.add_turn(chat_id, "assistant", "hola, en que te ayudo?")
    waha = FakeWahaClient()
    llm = FakeLlmClient()

    result = reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=_enabled_config(), store=store)

    assert result is None
    assert waha.calls == []
    assert llm.calls == []


def test_reply_after_activation_answers_the_pending_message() -> None:
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.set_bot_enabled(chat_id, True)
    store.add_turn(chat_id, "user", "hola, siguen ahi?")
    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text="claro, seguimos por aca")

    result = reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=_enabled_config(), store=store)

    assert result is not None
    assert result["reply"] == "claro, seguimos por aca"
    assert waha.calls == [(chat_id, "claro, seguimos por aca", "default")]
    # El LLM ve el mensaje pendiente como turno actual, no repetido dentro del historial.
    assert llm.calls[0][1] == []
    assert llm.calls[0][2] == "hola, siguen ahi?"


def test_reply_after_activation_does_not_duplicate_the_pending_user_turn() -> None:
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.set_bot_enabled(chat_id, True)
    store.add_turn(chat_id, "user", "hola, siguen ahi?")
    waha = FakeWahaClient()
    llm = FakeLlmClient()

    reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=_enabled_config(), store=store)

    full_history = store.get_full_history(chat_id)
    user_turns = [m for m in full_history if m["role"] == "user"]
    assert len(user_turns) == 1
    assert [m["role"] for m in full_history] == ["user", "assistant"]


def test_reply_after_activation_does_nothing_if_chat_got_disabled_again() -> None:
    """El catch-up de rate limit (`_rate_limit_catchup`) también llama a esta función — si un
    admin desactiva el chat en la ventana entre que se programó el timer y que disparó, no debe
    mandar una respuesta igual."""
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.set_bot_enabled(chat_id, True)
    store.add_turn(chat_id, "user", "hola, siguen ahi?")
    store.set_bot_enabled(chat_id, False)
    waha = FakeWahaClient()
    llm = FakeLlmClient()

    result = reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=_enabled_config(), store=store)

    assert result is None
    assert waha.calls == []
    assert llm.calls == []


def test_reply_after_activation_does_nothing_for_an_empty_pending_message() -> None:
    """Nota de voz recibida mientras el chat estaba apagado: se guarda como turno vacío
    (`_process` no transcribe en ese estado) — no hay nada real que contestar."""
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.set_bot_enabled(chat_id, True)
    store.add_turn(chat_id, "user", "")
    waha = FakeWahaClient()
    llm = FakeLlmClient()

    result = reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=_enabled_config(), store=store)

    assert result is None
    assert waha.calls == []
    assert llm.calls == []


def test_reply_after_activation_does_nothing_for_a_placeholder_pending_message() -> None:
    """Regresión: `_process` ya no guarda `""` para nota de voz/media no soportada mientras el
    chat está apagado, guarda un placeholder (`"[Nota de voz]"`/`"[Media no soportada]"`, ver
    `_placeholder_for_untranscribed_inbound`) — sigue sin ser texto real que el LLM deba
    contestar, aunque ya no esté vacío."""
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.set_bot_enabled(chat_id, True)
    store.add_turn(chat_id, "user", "[Nota de voz]")
    waha = FakeWahaClient()
    llm = FakeLlmClient()

    result = reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=_enabled_config(), store=store)

    assert result is None
    assert waha.calls == []
    assert llm.calls == []


def test_reply_after_activation_skipped_when_bot_disabled_globally() -> None:
    chat_id = "573001112233@c.us"
    store = ConversationStore()
    store.add_turn(chat_id, "user", "hola")
    waha = FakeWahaClient()
    llm = FakeLlmClient()
    config = BotConfig(enabled=False, max_history_turns=6)

    result = reply_after_activation(chat_id, waha, llm, FakeCrmClient(), config=config, store=store)

    assert result is None
    assert waha.calls == []
