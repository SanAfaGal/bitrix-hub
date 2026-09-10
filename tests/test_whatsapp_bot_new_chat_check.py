from app.flows.whatsapp_bot_new_chat_check import is_chat_new_in_waha
from app.waha.inbound import InboundMessage


class FakeWahaClient:
    """Simula el truncamiento por `limit` y el filtro `from_me` que hace Waha del lado del
    servidor — a diferencia del fake en `test_whatsapp_bot.py`, este sí recorta la lista para
    poder reproducir el bug de "mensajes consecutivos de un lado empujan al otro fuera de la
    ventana"."""

    def __init__(self, chat_messages: list[dict] | None) -> None:
        self._chat_messages = chat_messages
        self.calls: list[tuple[str, int, bool | None]] = []

    def get_chat_messages(
        self, chat_id: str, *, limit: int = 50, from_me: bool | None = None, session: str | None = None
    ) -> list[dict] | None:
        self.calls.append((chat_id, limit, from_me))
        if self._chat_messages is None:
            return None
        pool = (
            self._chat_messages
            if from_me is None
            else [m for m in self._chat_messages if bool(m.get("fromMe")) == from_me]
        )
        return pool[:limit]


def _inbound(message_id: str = "msg1") -> InboundMessage:
    return InboundMessage(chat_id="573001112233@c.us", text="hola", message_id=message_id, session="default")


def test_new_chat_with_empty_waha_history_is_new() -> None:
    waha = FakeWahaClient(chat_messages=[])
    assert is_chat_new_in_waha(_inbound(), waha) is True


def test_chat_with_history_from_both_sides_is_not_new() -> None:
    waha = FakeWahaClient(
        chat_messages=[
            {"id": "wa_prior_in", "fromMe": False, "body": "hola, ya habia escrito antes"},
            {"id": "wa_prior_out", "fromMe": True, "body": "hola! como te ayudo?"},
            {"id": "msg1", "fromMe": False, "body": "hola"},
        ]
    )
    assert is_chat_new_in_waha(_inbound(), waha) is False


def test_chat_with_only_customer_side_history_is_new() -> None:
    waha = FakeWahaClient(
        chat_messages=[
            {"id": "wa_prior_in", "fromMe": False, "body": "hola, nadie me contesto"},
            {"id": "msg1", "fromMe": False, "body": "hola"},
        ]
    )
    assert is_chat_new_in_waha(_inbound(), waha) is True


def test_fails_closed_when_either_waha_call_fails() -> None:
    waha = FakeWahaClient(chat_messages=None)
    assert is_chat_new_in_waha(_inbound(), waha) is False


def test_multiple_consecutive_incoming_messages_do_not_hide_prior_outgoing_message() -> None:
    """Bug real: antes de este fix, una sola llamada mezclada con `limit=10` se quedaba solo con
    los mensajes más recientes del chat. Si el cliente mandó 10+ mensajes seguidos después de que
    el asesor le escribió a mano, ese único mensaje del asesor quedaba fuera de la ventana y el
    chat se trataba como genuinamente nuevo (auto-activación indebida). Con llamadas separadas por
    `from_me`, el mensaje del asesor se sigue encontrando sin importar cuántos mensajes del cliente
    haya después."""
    recent_incoming = [
        {"id": f"in{i}", "fromMe": False, "body": f"mensaje {i}"} for i in range(10)
    ]
    older_history = [
        {"id": "asesor1", "fromMe": True, "body": "hola, en qué te ayudo?"},
        {"id": "in_first", "fromMe": False, "body": "hola, quiero info"},
    ]
    waha = FakeWahaClient(chat_messages=recent_incoming + older_history + [{"id": "msg1", "fromMe": False, "body": "hola"}])

    assert is_chat_new_in_waha(_inbound(message_id="msg1"), waha) is False
