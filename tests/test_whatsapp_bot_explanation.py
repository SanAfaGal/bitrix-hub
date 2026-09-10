from __future__ import annotations

from app.flows.whatsapp_bot import ConversationStore
from app.flows.whatsapp_bot_explanation import (
    maybe_handle_acceptance,
    maybe_handle_delayed_explanation_request,
    maybe_send_explanation,
)
from app.message_templates import store as templates_store
from tests.fakes import FakeCrmClient

_LINK_SECRET = "test-secret"
_PUBLIC_BASE_URL = "https://hub.example.com"


class FakeWahaClient:
    def __init__(self, send_result: bool = True) -> None:
        self.send_result = send_result
        self.calls: list[tuple[str, str, str | None]] = []
        self.voice_calls: list[tuple[str, str, str | None]] = []

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        self.calls.append((chat_id, text, session))
        return self.send_result

    def send_voice(self, chat_id: str, audio_base64: str, *, session: str | None = None, **_: object) -> bool:
        self.voice_calls.append((chat_id, audio_base64, session))
        return True

    def get_chat_messages(
        self, chat_id: str, *, limit: int = 50, from_me: bool | None = None, session: str | None = None
    ) -> list[dict]:
        # Todos los tests de este archivo simulan una conversación ya activa (el cliente
        # acaba de escribir "si"/etc.) — con historial real de por medio, el cap anti-baneo de
        # `app.waha.outbound_throttle` (solo aplica a contactos que nunca respondieron) no debe
        # activarse acá.
        return [{"id": "prev", "fromMe": False, "body": "hola"}]


# ── maybe_send_explanation ──────────────────────────────────────────────


def test_sends_text_audio_and_ask_acceptance_in_one_go_without_asking_first() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()

    handled = maybe_send_explanation("573001112233@c.us", "default", waha, store)

    assert handled is True
    assert [c[1] for c in waha.calls] == [
        templates_store.DEFAULT_TEMPLATES["whatsapp_process_explanation"],
        templates_store.DEFAULT_TEMPLATES["whatsapp_ask_acceptance"],
    ]
    assert len(waha.voice_calls) == 1
    assert store.get_explanation_sent("573001112233@c.us") is True

    history = store.get_full_history("573001112233@c.us")
    assert [h["role"] for h in history] == ["assistant", "assistant", "assistant"]


def test_does_not_resend_explanation_once_already_sent() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_send_explanation("573001112233@c.us", "default", waha, store)

    assert handled is False
    assert waha.calls == []
    assert waha.voice_calls == []


# ── maybe_handle_delayed_explanation_request ────────────────────────────


def test_sends_audio_when_person_asks_for_explanation_before_it_was_sent() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()

    handled = maybe_handle_delayed_explanation_request("573001112233@c.us", True, waha, "default", store)

    assert handled is True
    assert len(waha.voice_calls) == 1
    assert [c[1] for c in waha.calls] == [templates_store.DEFAULT_TEMPLATES["whatsapp_ask_acceptance"]]
    assert store.get_explanation_sent("573001112233@c.us") is True


def test_does_not_send_audio_when_not_requested() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()

    handled = maybe_handle_delayed_explanation_request("573001112233@c.us", False, waha, "default", store)

    assert handled is False
    assert waha.calls == []


def test_does_not_resend_when_explanation_already_sent() -> None:
    waha = FakeWahaClient()
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_delayed_explanation_request("573001112233@c.us", True, waha, "default", store)

    assert handled is False
    assert waha.calls == []


# ── maybe_handle_acceptance ──────────────────────────────────────────────


def test_sends_authorization_link_when_person_confirms() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(
        deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}},
        contacts={"5000": {"PHONE": "3001112233"}},
    )
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is True
    assert crm.authorization_status_updates == [("6000", "pendiente_firma")]
    history = store.get_full_history("573001112233@c.us")
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert history[0]["content"] == "si"


def test_does_not_handle_when_explanation_not_sent_yet() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}})
    store = ConversationStore()

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is False
    assert crm.authorization_status_updates == []


def test_does_not_handle_when_reply_is_not_a_clear_affirmation() -> None:
    waha = FakeWahaClient()
    crm = FakeCrmClient(deals={"6000": {"ID": "6000", "CONTACT_ID": "5000"}})
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us",
        "y esto tiene algun costo?",
        "6000",
        crm,
        waha,
        "default",
        _PUBLIC_BASE_URL,
        _LINK_SECRET,
        store,
    )

    assert handled is False
    assert crm.authorization_status_updates == []


def test_does_not_resend_link_once_authorization_already_pending_in_bitrix() -> None:
    """Respaldo cuando el tracking local se perdió (ej. reset de la base) pero Bitrix ya
    tiene `"pendiente_firma"` — un estado que solo escribe este mismo flujo, a diferencia del
    default ambiguo (`"pendiente_envio"`) que causó el bug real (ver docstring de la función)."""
    waha = FakeWahaClient()
    crm = FakeCrmClient(
        deals={"6000": {"ID": "6000", "CONTACT_ID": "5000", "AUTHORIZATION_STATUS": "pendiente_firma"}},
        contacts={"5000": {"PHONE": "3001112233"}},
    )
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is False
    assert crm.authorization_status_updates == []
    assert waha.calls == []


def test_sends_link_when_bitrix_has_the_ambiguous_default_status_but_never_actually_sent() -> None:
    """Reproduce el bug real: Bitrix trae `"pendiente_envio"` (default del picklist) desde que
    se crea el deal, sin que este flujo haya mandado nada todavía — antes, `is None` nunca
    daba `True` y el link no se mandaba nunca. Ahora el gate no depende de ese campo."""
    waha = FakeWahaClient()
    crm = FakeCrmClient(
        deals={"6000": {"ID": "6000", "CONTACT_ID": "5000", "AUTHORIZATION_STATUS": "pendiente_envio"}},
        contacts={"5000": {"PHONE": "3001112233"}},
    )
    store = ConversationStore()
    store.set_explanation_sent("573001112233@c.us")

    handled = maybe_handle_acceptance(
        "573001112233@c.us", "si", "6000", crm, waha, "default", _PUBLIC_BASE_URL, _LINK_SECRET, store
    )

    assert handled is True
    assert crm.authorization_status_updates == [("6000", "pendiente_firma")]
    assert store.get_authorization_link_sent("573001112233@c.us") is True
