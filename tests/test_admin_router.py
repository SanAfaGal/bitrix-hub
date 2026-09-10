from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin import auth as admin_auth
from app.admin import router as admin_router
from app.admin.settings import AdminSettings
from app.flows.whatsapp_bot import ConversationStore
from app.main import app
from app.message_templates import db as templates_db
from app.message_templates import store as templates_store
from app.message_templates.models import Base
from app.shared import rate_limit as rate_limit_module

_CREDENTIALS = AdminSettings(username="admin", password="secret123", session_secret="test-secret")
_FIRST_TEMPLATE_KEY = templates_store.TEMPLATE_SECTIONS[0]["keys"][0]


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """El rate limit del login es en memoria de proceso — sin esto, los tests de este archivo
    comparten el mismo bucket (TestClient no trae IP real) y se agotan entre sí."""
    rate_limit_module._hits.clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """DB de plantillas en SQLite en memoria (una sola conexión compartida vía StaticPool,
    para que sobreviva entre requests) y credenciales fijas, sin depender de env vars reales."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(templates_db, "SessionLocal", sessionmaker(bind=engine, future=True))
    monkeypatch.setattr(admin_auth, "load_admin_settings", lambda: _CREDENTIALS)
    return TestClient(app)


def _log_in(client: TestClient) -> None:
    response = client.post("/admin/login", data={"username": "admin", "password": "secret123"})
    assert response.status_code == 200  # sigue el redirect y termina en /admin/templates/<primera key>


def test_templates_index_redirects_to_login_when_not_authenticated(client: TestClient) -> None:
    response = client.get("/admin/templates", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_login_with_wrong_credentials_shows_error(client: TestClient) -> None:
    response = client.post("/admin/login", data={"username": "admin", "password": "incorrecta"})

    assert response.status_code == 200
    assert "incorrectos" in response.text


def test_login_is_rate_limited_after_too_many_attempts(client: TestClient) -> None:
    for _ in range(10):
        response = client.post("/admin/login", data={"username": "admin", "password": "incorrecta"})
        assert response.status_code == 200

    blocked = client.post("/admin/login", data={"username": "admin", "password": "incorrecta"})

    assert blocked.status_code == 429


def test_login_redirects_to_first_template(client: TestClient) -> None:
    response = client.post("/admin/login", data={"username": "admin", "password": "secret123"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/templates/{_FIRST_TEMPLATE_KEY}"


def test_templates_index_redirects_to_first_template_when_authenticated(client: TestClient) -> None:
    _log_in(client)

    response = client.get("/admin/templates", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/templates/{_FIRST_TEMPLATE_KEY}"


def test_template_editor_page_is_reachable(client: TestClient) -> None:
    _log_in(client)

    response = client.get(f"/admin/templates/{_FIRST_TEMPLATE_KEY}")

    assert response.status_code == 200
    assert "Plantillas" in response.text
    assert templates_store.TEMPLATE_LABELS[_FIRST_TEMPLATE_KEY] in response.text


def test_unknown_template_key_redirects_to_first_template(client: TestClient) -> None:
    _log_in(client)

    response = client.get("/admin/templates/no_existe", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/templates/{_FIRST_TEMPLATE_KEY}"


def test_config_page_does_not_expose_system_prompt_as_a_template(client: TestClient) -> None:
    _log_in(client)

    response = client.get(f"/admin/templates/{templates_store.CONFIG_KEY}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/templates/{_FIRST_TEMPLATE_KEY}"


def test_edit_template_persists_and_is_used_by_the_bot(client: TestClient) -> None:
    _log_in(client)

    response = client.post(f"/admin/templates/{_FIRST_TEMPLATE_KEY}", data={"content": "Texto editado desde el panel"})

    assert response.status_code == 200
    assert "Guardado." in response.text
    assert "Texto editado desde el panel" in response.text
    assert templates_store.get_template(_FIRST_TEMPLATE_KEY) == "Texto editado desde el panel"


def test_edit_template_rejects_empty_content(client: TestClient) -> None:
    _log_in(client)

    response = client.post(f"/admin/templates/{_FIRST_TEMPLATE_KEY}", data={"content": ""})

    assert response.status_code == 200
    assert "no puede estar vacío" in response.text
    assert templates_store.get_template(_FIRST_TEMPLATE_KEY) == templates_store.DEFAULT_TEMPLATES[_FIRST_TEMPLATE_KEY]


def test_restore_template_resets_to_default(client: TestClient) -> None:
    _log_in(client)
    client.post(f"/admin/templates/{_FIRST_TEMPLATE_KEY}", data={"content": "Editado"})

    response = client.post(f"/admin/templates/{_FIRST_TEMPLATE_KEY}/restore")

    assert response.status_code == 200
    assert "Restaurado al valor por defecto." in response.text
    assert templates_store.get_template(_FIRST_TEMPLATE_KEY) == templates_store.DEFAULT_TEMPLATES[_FIRST_TEMPLATE_KEY]


def test_edit_unknown_template_key_redirects(client: TestClient) -> None:
    _log_in(client)

    response = client.post("/admin/templates/no_existe", data={"content": "texto"}, follow_redirects=False)

    assert response.status_code == 303


def test_config_page_requires_login(client: TestClient) -> None:
    response = client.get("/admin/config", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_config_page_shows_system_prompt(client: TestClient) -> None:
    _log_in(client)

    response = client.get("/admin/config")

    assert response.status_code == 200
    assert "Configuración del bot" in response.text
    assert templates_store.DEFAULT_TEMPLATES[templates_store.CONFIG_KEY][:40] in response.text


def test_edit_config_persists(client: TestClient) -> None:
    _log_in(client)

    response = client.post("/admin/config", data={"content": "Nuevo comportamiento del bot"})

    assert response.status_code == 200
    assert "Guardado." in response.text
    assert templates_store.get_template(templates_store.CONFIG_KEY) == "Nuevo comportamiento del bot"


def test_restore_config_resets_to_default(client: TestClient) -> None:
    _log_in(client)
    client.post("/admin/config", data={"content": "Editado"})

    response = client.post("/admin/config/restore")

    assert response.status_code == 200
    assert templates_store.get_template(templates_store.CONFIG_KEY) == templates_store.DEFAULT_TEMPLATES[
        templates_store.CONFIG_KEY
    ]


def test_logout_then_templates_page_redirects_again(client: TestClient) -> None:
    _log_in(client)

    client.post("/admin/logout")
    response = client.get(f"/admin/templates/{_FIRST_TEMPLATE_KEY}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_prospects_list_requires_login(client: TestClient) -> None:
    response = client.get("/admin/prospects", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_prospects_list_shows_chats(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola, quiero vender mi apto")
    store.set_confirmed_identity("573001112233@c.us", "Ana", "573001112233")
    store.set_deal_id("573001112233@c.us", "42")
    monkeypatch.setattr(admin_router, "conversation_store", store)

    _log_in(client)
    response = client.get("/admin/prospects")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "Deal 42" in response.text
    assert "/admin/prospects/573001112233@c.us" in response.text


def test_prospects_list_shows_empty_state(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_router, "conversation_store", ConversationStore())

    _log_in(client)
    response = client.get("/admin/prospects")

    assert response.status_code == 200
    assert "Todavía no hay conversaciones" in response.text


def test_prospect_detail_shows_full_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ConversationStore(max_history_turns=1)
    chat_id = "573001112233@c.us"
    store.add_turn(chat_id, "user", "hola")
    store.add_turn(chat_id, "assistant", "hola, en qué te ayudo")
    store.add_turn(chat_id, "user", "quiero vender un apto")
    store.set_confirmed_identity(chat_id, "Ana", "573001112233")
    monkeypatch.setattr(admin_router, "conversation_store", store)

    _log_in(client)
    response = client.get(f"/admin/prospects/{chat_id}")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "hola" in response.text
    assert "quiero vender un apto" in response.text


def test_prospect_detail_keeps_the_chat_list_visible(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Layout tipo WhatsApp Web: la lista sigue visible aunque haya un chat seleccionado."""
    store = ConversationStore()
    store.add_turn("111@c.us", "user", "chat uno")
    store.add_turn("222@c.us", "user", "chat dos")
    monkeypatch.setattr(admin_router, "conversation_store", store)

    _log_in(client)
    response = client.get("/admin/prospects/111@c.us")

    assert response.status_code == 200
    assert "chat uno" in response.text  # burbuja del hilo seleccionado (111@c.us)
    assert "/admin/prospects/222@c.us" in response.text  # fila del otro chat sigue en la lista
    assert 'prospect-row--active' in response.text


def test_prospect_detail_requires_login(client: TestClient) -> None:
    response = client.get("/admin/prospects/573001112233@c.us", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_prospects_list_shows_bot_off_badge_by_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ConversationStore()
    store.add_turn("573001112233@c.us", "user", "hola")
    monkeypatch.setattr(admin_router, "conversation_store", store)

    _log_in(client)
    response = client.get("/admin/prospects")

    assert response.status_code == 200
    assert "Bot: OFF" in response.text
    assert "Bot: ON" not in response.text


def test_prospect_detail_shows_bot_on_badge_and_deactivate_form(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    store.add_turn(chat_id, "user", "hola")
    store.set_bot_enabled(chat_id, True)
    monkeypatch.setattr(admin_router, "conversation_store", store)

    _log_in(client)
    response = client.get(f"/admin/prospects/{chat_id}")

    assert response.status_code == 200
    assert "Bot: ON" in response.text
    assert f"/admin/prospects/{chat_id}/bot/deactivate" in response.text


def test_activate_bot_requires_login(client: TestClient) -> None:
    response = client.post("/admin/prospects/573001112233@c.us/bot/activate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_deactivate_bot_requires_login(client: TestClient) -> None:
    response = client.post("/admin/prospects/573001112233@c.us/bot/deactivate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_activate_bot_seeds_history_and_enables_bot(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    monkeypatch.setattr(admin_router, "conversation_store", store)
    monkeypatch.setattr(admin_router, "get_waha_client", lambda: object())
    monkeypatch.setattr(admin_router, "get_llm_client", lambda: object())
    seed_calls: list[tuple] = []
    monkeypatch.setattr(
        admin_router,
        "seed_history_from_waha",
        lambda s, w, l, cid: seed_calls.append((s, w, l, cid))
        or {"seeded": True, "messages_imported": 3, "analysis": None},
    )

    _log_in(client)
    response = client.post(f"/admin/prospects/{chat_id}/bot/activate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/prospects/{chat_id}"
    assert store.get_bot_enabled(chat_id) is True
    assert len(seed_calls) == 1
    assert seed_calls[0][0] is store
    assert seed_calls[0][3] == chat_id


def test_activate_bot_holds_chat_lock_while_seeding_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin el lock, un mensaje real llegando por el webhook al mismo tiempo que un admin activa el
    chat podía pisarse con `seed_history_from_waha` (`clear_messages`/`add_turn` de ambos lados)."""
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    monkeypatch.setattr(admin_router, "conversation_store", store)
    monkeypatch.setattr(admin_router, "get_waha_client", lambda: object())
    monkeypatch.setattr(admin_router, "get_llm_client", lambda: object())
    monkeypatch.setattr(admin_router, "reply_after_activation", lambda *a, **k: None)
    lock_was_held: list[bool] = []

    def _fake_seed(s, w, l, cid):
        lock_was_held.append(store.chat_lock(chat_id).locked())
        return {"seeded": True, "messages_imported": 0, "analysis": None}

    monkeypatch.setattr(admin_router, "seed_history_from_waha", _fake_seed)

    _log_in(client)
    response = client.post(f"/admin/prospects/{chat_id}/bot/activate", follow_redirects=False)

    assert response.status_code == 303
    assert lock_was_held == [True]


def test_activate_bot_replies_to_the_pending_message(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Al activar, si el cliente tenía un mensaje sin responder, el bot lo contesta de una vez —
    no hace falta esperar a que el cliente escriba de nuevo."""
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    monkeypatch.setattr(admin_router, "conversation_store", store)
    monkeypatch.setattr(admin_router, "get_waha_client", lambda: object())
    monkeypatch.setattr(admin_router, "get_llm_client", lambda: object())
    monkeypatch.setattr(admin_router, "get_crm_client", lambda: object())
    monkeypatch.setattr(
        admin_router, "seed_history_from_waha", lambda s, w, l, cid: {"seeded": False, "messages_imported": 0, "analysis": None}
    )
    reply_calls: list[tuple] = []
    monkeypatch.setattr(
        admin_router,
        "reply_after_activation",
        lambda cid, w, l, c, *, store: reply_calls.append((cid, w, l, c, store)) or {"ok": True},
    )

    _log_in(client)
    response = client.post(f"/admin/prospects/{chat_id}/bot/activate", follow_redirects=False)

    assert response.status_code == 303
    assert len(reply_calls) == 1
    assert reply_calls[0][0] == chat_id
    assert reply_calls[0][4] is store


def test_activate_bot_is_a_noop_when_already_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarda contra el doble clic en "Activar" — si ya estaba prendido, no reimporta el historial."""
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    store.set_bot_enabled(chat_id, True)
    monkeypatch.setattr(admin_router, "conversation_store", store)
    seed_calls: list[tuple] = []
    monkeypatch.setattr(
        admin_router,
        "seed_history_from_waha",
        lambda s, w, l, cid: seed_calls.append((s, w, l, cid)) or {"seeded": False, "messages_imported": 0, "analysis": None},
    )

    _log_in(client)
    response = client.post(f"/admin/prospects/{chat_id}/bot/activate", follow_redirects=False)

    assert response.status_code == 303
    assert store.get_bot_enabled(chat_id) is True
    assert seed_calls == []


def test_activate_bot_handles_misconfigured_integration_gracefully(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si Waha/LLM no están configurados, la ruta no debe romper el panel — solo activa sin sembrar historial."""
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    monkeypatch.setattr(admin_router, "conversation_store", store)

    def _raise() -> None:
        raise RuntimeError("falta configuración")

    monkeypatch.setattr(admin_router, "get_waha_client", _raise)

    _log_in(client)
    response = client.post(f"/admin/prospects/{chat_id}/bot/activate", follow_redirects=False)

    assert response.status_code == 303
    assert store.get_bot_enabled(chat_id) is True


def test_deactivate_bot_disables_bot(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ConversationStore()
    chat_id = "573001112233@c.us"
    store.set_bot_enabled(chat_id, True)
    monkeypatch.setattr(admin_router, "conversation_store", store)

    _log_in(client)
    response = client.post(f"/admin/prospects/{chat_id}/bot/deactivate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/prospects/{chat_id}"
    assert store.get_bot_enabled(chat_id) is False
