from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
            self.calls: list[tuple[str, list[str], str | None]] = []

        def send_text_sequence(self, chat_id: str, messages: list[str], session: str | None = None) -> bool:
            self.calls.append((chat_id, messages, session))
            return True

    monkeypatch.setattr("app.flows.router.get_crm_client", lambda: fake_crm)
    monkeypatch.setattr("app.flows.router.get_waha_client", lambda: FakeWahaClient())
    monkeypatch.setattr("app.flows.router.load_public_base_url", lambda: "https://hub.example.com")
    monkeypatch.setattr("app.flows.router.load_form_link_secret", lambda: "test-secret")

    response = client.post("/webhook/deal-stage-broker-auth", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "deal_id": "42", "contact_id": "7", "chat_id": "573001112233@c.us"}


def test_webhook_deal_stage_broker_auth_requires_deal_id() -> None:
    response = client.post("/webhook/deal-stage-broker-auth", data={})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Falta ID"}


def test_webhook_waha_message_skips_when_not_applicable() -> None:
    event = {"event": "session.status", "session": "default", "payload": {}}

    response = client.post("/webhook/waha-message", json=event)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "skipped": "not_applicable"}


def test_webhook_waha_message_skips_when_bot_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=False, max_history_turns=6, system_prompt="system"),
    )

    response = client.post("/webhook/waha-message", json=_WAHA_MESSAGE_EVENT)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "chat_id": "573001112233@c.us", "skipped": "bot_disabled"}


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
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6, system_prompt="system"),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", lambda: FakeLlmClient())
    monkeypatch.setattr("app.waha.router.get_crm_client", lambda: FakeCrmClient())
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

    class FakeLlmClient:
        def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
            return json_module.dumps(
                {"reply": "listo, algo mas?", "fields": {"address": "Calle 10 # 20-30"}}
            )

    fake_crm = FakeCrmClient()
    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6, system_prompt="system"),
    )
    monkeypatch.setattr("app.waha.router.get_llm_client", lambda: FakeLlmClient())
    monkeypatch.setattr("app.waha.router.get_crm_client", lambda: fake_crm)
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

    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6, system_prompt="system"),
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

    monkeypatch.setattr(
        "app.waha.router.load_bot_config",
        lambda: BotConfig(enabled=True, max_history_turns=6, system_prompt="system"),
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


def test_webhook_deal_stage_broker_auth_logs_error_when_public_base_url_missing(monkeypatch, caplog) -> None:
    def raise_missing_public_base_url():
        raise RuntimeError("Falta variable de entorno: HUB_PUBLIC_BASE_URL")

    monkeypatch.setattr("app.flows.router.get_crm_client", lambda: FakeCrmClient())
    monkeypatch.setattr("app.flows.router.get_waha_client", lambda: object())
    monkeypatch.setattr("app.flows.router.load_public_base_url", raise_missing_public_base_url)

    with caplog.at_level("ERROR"):
        response = client.post("/webhook/deal-stage-broker-auth", data={"data[FIELDS][ID]": "42"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Falta variable de entorno: HUB_PUBLIC_BASE_URL"}
    assert any("42" in record.message and "HUB_PUBLIC_BASE_URL" in record.message for record in caplog.records)
