from __future__ import annotations

from app.flows.whatsapp_bot import BotConfig, ConversationStore
from app.flows.whatsapp_bot_history_seed import seed_history_from_waha


class FakeWahaClient:
    def __init__(self, messages: list[dict] | None) -> None:
        self._messages = messages
        self.calls: list[tuple[str, int, str | None]] = []

    def get_chat_messages(self, chat_id: str, *, limit: int = 50, session: str | None = None) -> list[dict] | None:
        self.calls.append((chat_id, limit, session))
        return self._messages


class FakeLlmClient:
    def __init__(self, reply_text: str | None) -> None:
        self.reply_text = reply_text
        self.calls: list[tuple[str, list[dict], str]] = []

    def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
        self.calls.append((system_prompt, history, user_text))
        return self.reply_text


_ANALYSIS_JSON = (
    '{"client_full_name": "Carlos Ramírez", "client_phone": "573001112233", '
    '"process_explained": true, "authorization_mentioned": true, "summary": "resumen"}'
)

_PRIOR_MESSAGES = [
    {"id": "1", "fromMe": False, "body": "hola, quiero vender mi apto", "timestamp": 100},
    {"id": "2", "fromMe": True, "body": "claro, soy Andrea, le explico el proceso", "timestamp": 101},
    {"id": "3", "fromMe": False, "body": "listo, gracias", "timestamp": 102},
]


def _config(**overrides) -> BotConfig:
    base = dict(enabled=True, max_history_turns=6, history_analysis_limit=40)
    base.update(overrides)
    return BotConfig(**base)


def test_seed_history_imports_turns_and_sets_lead_fields_from_analysis(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config(max_history_turns=6)
    )
    store = ConversationStore(max_history_turns=6)
    waha = FakeWahaClient(_PRIOR_MESSAGES)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert result["seeded"] is True
    assert result["messages_imported"] == 3
    assert result["analysis"]["client_full_name"] == "Carlos Ramírez"

    history = store.get_full_history("573001112233@c.us")
    assert [m["content"] for m in history] == [
        "hola, quiero vender mi apto",
        "claro, soy Andrea, le explico el proceso",
        "listo, gracias",
    ]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]

    assert store.get_confirmed_identity("573001112233@c.us") == ("Carlos Ramírez", "573001112233")
    assert store.get_explanation_sent("573001112233@c.us") is True
    # authorization_mentioned (mera mención en la conversación) no implica que el link
    # REAL ya se mandó — ver docstring de seed_history_from_waha, Hallazgo 3 de la
    # revisión final.
    assert store.get_authorization_link_sent("573001112233@c.us") is False
    assert store.get_history_seeded("573001112233@c.us") is True

    assert waha.calls == [("573001112233@c.us", 40, "default")]


def test_seed_history_uses_the_session_passed_in(monkeypatch) -> None:
    """Sin esto, siempre consultaba la sesión default de Waha aunque el deployment tenga
    configurada otra (`WAHA_SESSION`) — a diferencia de `is_chat_new_in_waha`, que ya
    threadea `inbound.session`."""
    monkeypatch.setattr("app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config())
    store = ConversationStore()
    waha = FakeWahaClient(_PRIOR_MESSAGES)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    seed_history_from_waha(store, waha, llm, "573001112233@c.us", session="otra-sesion")

    assert waha.calls == [("573001112233@c.us", 40, "otra-sesion")]


def test_seed_history_does_not_overwrite_already_confirmed_identity(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config())
    store = ConversationStore(max_history_turns=6)
    store.set_confirmed_identity("573001112233@c.us", "Nombre Ya Confirmado", "573009998877")
    waha = FakeWahaClient(_PRIOR_MESSAGES)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert store.get_confirmed_identity("573001112233@c.us") == ("Nombre Ya Confirmado", "573009998877")


def test_seed_history_no_op_when_waha_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config())
    store = ConversationStore(max_history_turns=6)
    waha = FakeWahaClient(None)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert result == {"seeded": False, "messages_imported": 0, "analysis": None}
    assert store.get_full_history("573001112233@c.us") == []
    assert llm.calls == []
    # Se marca igual: no hay nada que importar, evita reintentar Waha en cada reactivación.
    assert store.get_history_seeded("573001112233@c.us") is True


def test_seed_history_no_op_when_waha_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config())
    store = ConversationStore(max_history_turns=6)
    waha = FakeWahaClient([])
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert result == {"seeded": False, "messages_imported": 0, "analysis": None}
    assert llm.calls == []


def test_seed_history_no_op_when_already_seeded(monkeypatch) -> None:
    """La señal de idempotencia es `history_seeded` (columna dedicada), no si el chat ya
    tiene historial local — un chat puede tener historial local (mensajes guardados durante
    el período con `bot_enabled=False`) sin que Waha ya se haya importado, ver el test de
    abajo que cubre justo ese caso (el bug del Hallazgo Crítico de la revisión final)."""
    monkeypatch.setattr("app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config())
    store = ConversationStore(max_history_turns=6)
    store.add_turn("573001112233@c.us", "user", "ya hay algo acá")
    store.set_history_seeded("573001112233@c.us")
    waha = FakeWahaClient(_PRIOR_MESSAGES)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert result == {"seeded": False, "messages_imported": 0, "analysis": None}
    # No se reimporta ni se reanaliza en una reactivación ya seedeada.
    assert waha.calls == []
    assert llm.calls == []
    history = store.get_full_history("573001112233@c.us")
    assert len(history) == 1


def test_seed_history_imports_from_waha_and_replaces_local_disabled_period_messages(monkeypatch) -> None:
    """Reproduce el Hallazgo Crítico de la revisión final: un chat que ya tiene historial
    local (mensajes guardados mientras `bot_enabled=False`, ver `_process()` en
    whatsapp_bot.py) pero que TODAVÍA no tiene `history_seeded=True` debe seguir yendo a
    buscar el historial real a Waha, analizarlo con el LLM e importarlo — reemplazando el
    historial local del período desactivado (subconjunto de lo que Waha devuelve), no
    duplicándolo."""
    monkeypatch.setattr(
        "app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config(max_history_turns=6)
    )
    store = ConversationStore(max_history_turns=6)
    # Simula lo que `_process()` ya guardó mientras el chat estaba desactivado.
    store.add_turn("573001112233@c.us", "user", "hola, quiero vender mi apto")
    assert store.get_history_seeded("573001112233@c.us") is False

    waha = FakeWahaClient(_PRIOR_MESSAGES)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert result["seeded"] is True
    assert result["messages_imported"] == 3
    assert waha.calls == [("573001112233@c.us", 40, "default")]
    assert len(llm.calls) == 1

    history = store.get_full_history("573001112233@c.us")
    # El turno local del período desactivado quedó reemplazado por los 3 turnos de Waha,
    # no duplicado (no hay 4 turnos).
    assert [m["content"] for m in history] == [
        "hola, quiero vender mi apto",
        "claro, soy Andrea, le explico el proceso",
        "listo, gracias",
    ]
    assert store.get_history_seeded("573001112233@c.us") is True


def test_seed_history_truncates_imported_turns_to_max_history_turns_times_two(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config(max_history_turns=1)
    )
    store = ConversationStore(max_history_turns=1)
    waha = FakeWahaClient(_PRIOR_MESSAGES)  # 3 mensajes, tope debe quedar en 2 (max_history_turns=1 * 2)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    assert result["messages_imported"] == 2
    history = store.get_full_history("573001112233@c.us")
    # Se conservan los más recientes, en orden cronológico.
    assert [m["content"] for m in history] == [
        "claro, soy Andrea, le explico el proceso",
        "listo, gracias",
    ]


def test_seed_history_imports_zero_turns_when_max_history_turns_is_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.flows.whatsapp_bot_history_seed.load_bot_config", lambda: _config(max_history_turns=0)
    )
    store = ConversationStore(max_history_turns=6)
    waha = FakeWahaClient(_PRIOR_MESSAGES)
    llm = FakeLlmClient(_ANALYSIS_JSON)

    result = seed_history_from_waha(store, waha, llm, "573001112233@c.us")

    # Un tope de cero turnos no debe interpretarse como "sin tope": no se
    # importa ningún turno, aunque Waha sí tenía mensajes.
    assert result["messages_imported"] == 0
    assert store.get_full_history("573001112233@c.us") == []
