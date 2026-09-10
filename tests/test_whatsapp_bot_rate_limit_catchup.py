from __future__ import annotations

import json
import threading

import pytest

from app.flows.whatsapp_bot import BotConfig, ConversationStore, process
from app.flows.whatsapp_bot_conversation_store import RATE_LIMIT_COOLDOWN_SECONDS
from app.message_templates import store as templates_store
from app.waha.inbound import InboundMessage
from tests.fakes import FakeCrmClient


@pytest.fixture(autouse=True, scope="module")
def _warm_templates_mysql_cooldown() -> None:
    """La primera llamada a `templates_store.get_template` sin MySQL real disponible tarda unos
    segundos (falla la conexión antes de caer al default) y recién ahí entra en cooldown — ver
    `app.message_templates.store._is_in_cooldown`. Se dispara acá, una sola vez y fuera de
    cualquier `Timer.join(timeout=...)`, para que esa demora nunca compita con el timeout de los
    joins de más abajo (que corren en background thread, real, no en el thread del test)."""
    templates_store.get_template("whatsapp_system_prompt")


class FakeWahaClient:
    def __init__(self, send_result: bool = True) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.send_result


class FakeLlmClient:
    def __init__(self, reply_text: str | None = "perdon la demora, contame mas") -> None:
        self.reply_text = reply_text
        self.calls: list[tuple[str, list[dict], str]] = []

    def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
        self.calls.append((system_prompt, history, user_text))
        if self.reply_text is None:
            return None
        return json.dumps({"reply": self.reply_text, "fields": {}})


class ImmediateTimer:
    """Reemplaza `threading.Timer` en tests — corre el callback en un thread real ya mismo (sin
    esperar el delay), pero SIN bloquear `start()` — igual que el `Timer` real, que solo lanza el
    thread y vuelve. Correrlo en el mismo thread que llama a `process()` deadlockearía: `process()`
    todavía sostiene `store.chat_lock(chat_id)` en ese momento, y el catch-up necesita el mismo
    lock (ver `reply_after_activation`) — en producción nunca pasa porque el `Timer` real dispara
    mucho después de que `process()` ya devolvió y liberó el lock. Los tests deben hacer
    `timer.join()` (después de que `process()` retornó) para esperar a que el callback termine."""

    instances: list["ImmediateTimer"] = []

    def __init__(self, delay: float, target, args=(), kwargs=None) -> None:
        self.delay = delay
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = False
        self.started = False
        self._thread: threading.Thread | None = None
        ImmediateTimer.instances.append(self)

    def start(self) -> None:
        self.started = True
        self._thread = threading.Thread(target=self.target, args=self.args, kwargs=self.kwargs)
        self._thread.daemon = self.daemon
        self._thread.start()

    def join(self, timeout: float | None = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


@pytest.fixture(autouse=True)
def _reset_immediate_timer() -> None:
    ImmediateTimer.instances = []


def _inbound(message_id: str, text: str, chat_id: str = "573001112233@c.us") -> InboundMessage:
    return InboundMessage(
        chat_id=chat_id, text=text, message_id=message_id, session="default",
        is_audio=False, audio_media_path=None, is_unsupported=False,
    )


def _enabled_config() -> BotConfig:
    return BotConfig(enabled=True, max_history_turns=6)


def test_rate_limited_message_schedules_a_catchup_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", lambda self, chat_id: True)
    monkeypatch.setattr(threading, "Timer", ImmediateTimer)

    waha = FakeWahaClient()
    llm = FakeLlmClient()
    crm = FakeCrmClient()
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    store.set_bot_enabled(chat_id, True)  # crea la fila del lead, para que chat_exists sea True
    store.mark_message_received(chat_id)

    process(_inbound("msg1", "hola de nuevo"), waha, llm, crm, object(), config=_enabled_config(), store=store)

    assert len(ImmediateTimer.instances) == 1
    timer = ImmediateTimer.instances[0]
    assert timer.delay == RATE_LIMIT_COOLDOWN_SECONDS + 1
    assert timer.daemon is True
    # El propio ImmediateTimer ya corrió el callback en start() — que haya efectivamente respondido
    # se prueba en el siguiente test; acá solo importa que se programó con el delay correcto.


def test_rate_limited_message_gets_answered_after_the_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """El mensaje que quedó atrapado por el rate limit ya no depende de que el cliente escriba de
    nuevo — el catch-up programado lo contesta solo, pasado el cooldown."""
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", lambda self, chat_id: True)
    monkeypatch.setattr(threading, "Timer", ImmediateTimer)

    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text="tranqui, seguimos aca")
    crm = FakeCrmClient()
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    store.set_bot_enabled(chat_id, True)  # crea la fila del lead, para que chat_exists sea True
    store.mark_message_received(chat_id)

    result = process(
        _inbound("msg1", "hola de nuevo"), waha, llm, crm, object(), config=_enabled_config(), store=store
    )
    assert len(ImmediateTimer.instances) == 1
    ImmediateTimer.instances[0].join()  # espera al thread del catch-up (process() ya soltó el lock)

    assert result == {"ok": True, "chat_id": chat_id, "skipped": "rate_limited"}
    assert waha.calls == [(chat_id, "tranqui, seguimos aca", "default")]
    full_history = store.get_full_history(chat_id)
    assert [m["role"] for m in full_history] == ["user", "assistant"]


def test_catchup_does_nothing_if_a_later_message_already_got_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si para cuando el timer dispara ya se contestó (un mensaje posterior salió del cooldown
    normalmente), el catch-up no debe mandar una respuesta duplicada."""
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)
    monkeypatch.setattr(ConversationStore, "get_bot_enabled", lambda self, chat_id: True)

    captured_timer: list[ImmediateTimer] = []

    class _CapturingTimer(ImmediateTimer):
        def start(self) -> None:
            captured_timer.append(self)
            # No corre el target todavía — simula que el timer sigue pendiente mientras,
            # en el medio, otro mensaje ya fue respondido normalmente.

    monkeypatch.setattr(threading, "Timer", _CapturingTimer)

    waha = FakeWahaClient()
    llm = FakeLlmClient(reply_text="ya te contesto")
    crm = FakeCrmClient()
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    store.set_bot_enabled(chat_id, True)  # crea la fila del lead, para que chat_exists sea True
    store.mark_message_received(chat_id)

    process(_inbound("msg1", "hola de nuevo"), waha, llm, crm, object(), config=_enabled_config(), store=store)
    assert len(captured_timer) == 1

    # Ya se respondió a mano (ej. otro mensaje normal, o un asesor) antes de que el timer dispare.
    store.add_turn(chat_id, "assistant", "ya te ayudo un asesor")

    captured_timer[0].target(*captured_timer[0].args, **captured_timer[0].kwargs)

    assert waha.calls == []
