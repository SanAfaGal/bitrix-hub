from __future__ import annotations

from fastapi.testclient import TestClient

from app.flows import whatsapp_bot
from app.flows.whatsapp_bot import BotConfig
from app.main import app
from app.waha.deps import get_waha_client
from app.xposure.deps import get_xposure_client
from app.xposure.models import PropertySearchResult
from tests.fakes import FakeCrmClient

client = TestClient(app)


def _waha_message_event(message_id: str, text: str = "hola", chat_id: str = "573001112233@c.us") -> dict:
    return {
        "event": "message",
        "session": "default",
        "payload": {
            "id": message_id,
            "from": chat_id,
            "fromMe": False,
            "hasMedia": False,
            "body": text,
        },
    }


_WAHA_MESSAGE_EVENT = _waha_message_event("msg1")


def _disable_waha_webhook_secret(monkeypatch) -> None:
    """Los tests que no ejercitan el check de secreto en sí no deben depender de si
    WHATSAPP_WEBHOOK_SECRET está configurado en el .env local o no."""
    from app.waha.settings import WahaSettings

    monkeypatch.setattr(
        "app.waha.router.load_waha_settings",
        lambda: WahaSettings(base_url="http://waha", api_key=None, session="default", webhook_secret=None),
    )


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_integrations_reports_ok_and_error_per_integration(monkeypatch) -> None:
    monkeypatch.setattr("app.main._check_bitrix", lambda: True)
    monkeypatch.setattr("app.main._check_xposure", lambda: False)

    def _raise() -> bool:
        raise RuntimeError("Falta variable de entorno: WAHA_BASE_URL")

    monkeypatch.setattr("app.main._check_waha", _raise)
    monkeypatch.setattr("app.main._check_graph", lambda: True)

    response = client.get("/health/integrations")

    assert response.status_code == 200
    assert response.json() == {"bitrix": "ok", "xposure": "error", "waha": "error", "graph": "ok"}


def test_single_property_lookup() -> None:
    class FakeClient:
        def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None) -> PropertySearchResult:
            assert tax_roll == "12345"
            return PropertySearchResult(tax_roll=tax_roll, exists=True, mls="987654")

    app.dependency_overrides[get_xposure_client] = lambda: FakeClient()
    try:
        response = client.get("/properties/12345")
    finally:
        app.dependency_overrides.pop(get_xposure_client, None)

    assert response.status_code == 200
    assert response.json()["mls"] == "987654"


def test_webhook_deal_event_delegates_to_flow(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.router.load_bitrix_webhook_secret", lambda: None)
    monkeypatch.setattr("app.flows.router.get_crm_client", lambda: FakeCrmClient())
    monkeypatch.setattr("app.flows.router.get_xposure_client", lambda: None)

    response = client.post("/webhook/deal-event", data={"data[FIELDS][ID]": "42"})
    assert response.status_code == 200
    assert response.json()["deal_id"] == "42"


def test_webhook_deal_stage_broker_auth_sends_welcome_and_link(monkeypatch) -> None:
    fake_crm = FakeCrmClient(
        deals={"42": {"ID": "42", "CONTACT_ID": "7"}},
        contacts={"7": {"PHONE": "3001112233"}},
    )

    class FakeWahaClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []

        def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
            self.calls.append((chat_id, text, session))
            return True

        def get_chat_messages(
            self, chat_id: str, *, limit: int = 50, from_me: bool | None = None, session: str | None = None
        ) -> list[dict]:
            return []

    monkeypatch.setattr("app.flows.router.load_bitrix_webhook_secret", lambda: None)
    monkeypatch.setattr("app.flows.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.flows.router.get_waha_client", lambda: FakeWahaClient())
    monkeypatch.setattr("app.flows.router.load_public_base_url", lambda: "https://hub.example.com")
    monkeypatch.setattr("app.flows.router.load_form_link_secret", lambda: "test-secret")

    response = client.post("/webhook/deal-stage-broker-auth", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}


def test_webhook_deal_event_rejects_missing_or_wrong_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.router.load_bitrix_webhook_secret", lambda: "the-secret")

    missing = client.post("/webhook/deal-event", data={"data[FIELDS][ID]": "42"})
    wrong = client.post("/webhook/deal-event?secret=nope", data={"data[FIELDS][ID]": "42"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_webhook_deal_event_accepts_correct_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.router.load_bitrix_webhook_secret", lambda: "the-secret")
    monkeypatch.setattr("app.flows.router.get_crm_client", lambda: FakeCrmClient())
    monkeypatch.setattr("app.flows.router.get_xposure_client", lambda: None)

    response = client.post("/webhook/deal-event?secret=the-secret", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200


def test_webhook_deal_stage_broker_auth_requires_deal_id(monkeypatch) -> None:
    monkeypatch.setattr("app.flows.router.load_bitrix_webhook_secret", lambda: None)

    response = client.post("/webhook/deal-stage-broker-auth", data={})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Falta ID"}


def test_webhook_waha_message_skips_when_not_applicable(monkeypatch) -> None:
    _disable_waha_webhook_secret(monkeypatch)
    event = {"event": "session.status", "session": "default", "payload": {}}

    response = client.post("/webhook/waha-message", json=event)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "skipped": "not_applicable"}


def test_webhook_waha_message_rejects_missing_or_wrong_secret_when_configured(monkeypatch) -> None:
    from app.waha.settings import WahaSettings

    monkeypatch.setattr(
        "app.waha.router.load_waha_settings",
        lambda: WahaSettings(base_url="http://waha", api_key=None, session="default", webhook_secret="the-secret"),
    )

    missing = client.post("/webhook/waha-message", json=_WAHA_MESSAGE_EVENT)
    wrong = client.post("/webhook/waha-message?secret=nope", json=_WAHA_MESSAGE_EVENT)

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_webhook_waha_test_rejects_missing_or_wrong_secret_when_configured(monkeypatch) -> None:
    from app.waha.settings import WahaSettings

    monkeypatch.setattr(
        "app.waha.router.load_waha_settings",
        lambda: WahaSettings(base_url="http://waha", api_key=None, session="default", webhook_secret="the-secret"),
    )

    missing = client.post("/webhook/waha-test", params={"chat_id": "573001112233@c.us"})
    wrong = client.post("/webhook/waha-test", params={"chat_id": "573001112233@c.us", "secret": "nope"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_webhook_waha_message_skips_when_bot_disabled(monkeypatch) -> None:
    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=False, max_history_turns=6),
    )

    response = client.post("/webhook/waha-message", json=_WAHA_MESSAGE_EVENT)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled"}


def test_webhook_waha_message_skips_when_bot_disabled_for_chat(monkeypatch) -> None:
    """Activación por chat (opt-in, default apagado — Task 2): con el interruptor global
    prendido pero sin activar este chat en particular, el bot se queda callado (nada de
    bienvenida ni LLM) aunque el mensaje entrante sí quede guardado localmente."""
    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6),
    )
    chat_id = "573005556677@c.us"

    response = client.post("/webhook/waha-message", json=_waha_message_event("msg-disabled-chat", chat_id=chat_id))

    assert response.status_code == 200
    assert response.json() == {"ok": True, "chat_id": chat_id, "skipped": "bot_disabled_for_chat"}
    assert whatsapp_bot.conversation_store.get_history(chat_id) == [{"role": "user", "content": "hola"}]


def test_webhook_waha_message_replies_via_llm_when_enabled(monkeypatch) -> None:
    class FakeWahaClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []

        def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
            self.calls.append((chat_id, text, session))
            return True

    class FakeLlmClient:
        def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
            return "hola! como te ayudo?"

    fake_waha = FakeWahaClient()
    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", lambda: FakeLlmClient())
    monkeypatch.setattr("app.waha.router.get_crm_client", lambda: FakeCrmClient())
    monkeypatch.setattr("app.waha.router.get_transcription_client", lambda: object())
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)
    # Activación por chat (opt-in, default apagado desde Task 2) — este test ejercita el flujo
    # normal del bot, no el gate en sí, así que se activa a mano para el chat de prueba.
    whatsapp_bot.conversation_store.set_bot_enabled("573001112233@c.us", True)
    app.dependency_overrides[get_waha_client] = lambda: fake_waha
    try:
        response = client.post("/webhook/waha-message", json=_waha_message_event("msg-enabled"))
    finally:
        app.dependency_overrides.pop(get_waha_client, None)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "chat_id": "573001112233@c.us", "reply": "hola! como te ayudo?"}
    assert fake_waha.calls == [("573001112233@c.us", "hola! como te ayudo?", "default")]


def test_webhook_waha_message_creates_deal_and_updates_property_listing(monkeypatch) -> None:
    import json as json_module

    class FakeWahaClient:
        def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
            return True

        def send_voice(self, chat_id: str, audio_base64: str, *, session: str | None = None, **_: object) -> bool:
            return True

    class FakeLlmClient:
        def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
            return json_module.dumps(
                {
                    "reply": "listo, algo mas?",
                    "fields": {"address": "Calle 10 # 20-30"},
                    "client_full_name": "Juan Pérez",
                    "client_phone": "3009998877",
                }
            )

    fake_crm = FakeCrmClient()
    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", lambda: FakeLlmClient())
    monkeypatch.setattr("app.waha.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.waha.router.get_transcription_client", lambda: object())
    monkeypatch.setattr("app.flows.whatsapp_bot.maybe_send_first_contact_welcome", lambda *a, **k: False)
    whatsapp_bot.conversation_store.set_bot_enabled("573009998877@c.us", True)
    app.dependency_overrides[get_waha_client] = lambda: FakeWahaClient()
    try:
        response = client.post(
            "/webhook/waha-message",
            json=_waha_message_event("msg-crm", chat_id="573009998877@c.us"),
        )
    finally:
        app.dependency_overrides.pop(get_waha_client, None)

    assert response.status_code == 200
    assert response.json()["reply"] == "listo, algo mas?"
    assert fake_crm.contact_by_phone == {"573009998877": "5000"}
    assert fake_crm.deal_by_contact == {"5000": "6000"}
    assert fake_crm.property_listings["6000"].address == "Calle 10 # 20-30"


def test_webhook_waha_message_returns_error_when_llm_not_configured(monkeypatch) -> None:
    def raise_not_configured():
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Falta variable de entorno: LLM_API_KEY")

    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", raise_not_configured)
    app.dependency_overrides[get_waha_client] = lambda: object()
    try:
        response = client.post("/webhook/waha-message", json=_WAHA_MESSAGE_EVENT)
    finally:
        app.dependency_overrides.pop(get_waha_client, None)

    assert response.status_code == 200
    assert response.json() == {"ok": False, "chat_id": "573001112233@c.us", "error": "llm_not_configured"}


def test_webhook_waha_message_returns_error_when_crm_not_configured(monkeypatch) -> None:
    def raise_not_configured():
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Falta variable de entorno: BITRIX_WEBHOOK_URL")

    class FakeLlmClient:
        def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
            return "no debería llegar a llamarse"

    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", lambda: FakeLlmClient())
    monkeypatch.setattr("app.waha.router.get_crm_client", raise_not_configured)
    app.dependency_overrides[get_waha_client] = lambda: object()
    try:
        response = client.post("/webhook/waha-message", json=_waha_message_event("msg-crm-not-configured"))
    finally:
        app.dependency_overrides.pop(get_waha_client, None)

    assert response.status_code == 200
    assert response.json() == {"ok": False, "chat_id": "573001112233@c.us", "error": "crm_not_configured"}


def test_webhook_waha_message_returns_error_when_transcription_not_configured(monkeypatch) -> None:
    def raise_not_configured():
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Falta variable de entorno: TRANSCRIPTION_BASE_URL")

    class FakeLlmClient:
        def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
            return "no debería llegar a llamarse"

    _disable_waha_webhook_secret(monkeypatch)
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", lambda: FakeLlmClient())
    monkeypatch.setattr("app.waha.router.get_crm_client", lambda: FakeCrmClient())
    monkeypatch.setattr("app.waha.router.get_transcription_client", raise_not_configured)
    app.dependency_overrides[get_waha_client] = lambda: object()
    try:
        response = client.post("/webhook/waha-message", json=_waha_message_event("msg-transcription-not-configured"))
    finally:
        app.dependency_overrides.pop(get_waha_client, None)

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "chat_id": "573001112233@c.us",
        "error": "transcription_not_configured",
    }


def test_webhook_deal_stage_broker_auth_logs_error_when_public_base_url_missing(monkeypatch, caplog) -> None:
    def raise_missing_public_base_url():
        raise RuntimeError("Falta variable de entorno: HUB_PUBLIC_BASE_URL")

    monkeypatch.setattr("app.flows.router.load_bitrix_webhook_secret", lambda: None)
    monkeypatch.setattr("app.flows.router.get_crm_client", lambda: FakeCrmClient())
    monkeypatch.setattr("app.flows.router.get_waha_client", lambda: object())
    monkeypatch.setattr("app.flows.router.load_public_base_url", raise_missing_public_base_url)

    with caplog.at_level("ERROR"):
        response = client.post("/webhook/deal-stage-broker-auth", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Falta variable de entorno: HUB_PUBLIC_BASE_URL"}
    assert any("42" in record.message and "HUB_PUBLIC_BASE_URL" in record.message for record in caplog.records)
