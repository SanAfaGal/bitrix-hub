from __future__ import annotations

import pytest

from app.flows import whatsapp_bot
from app.forms import router as forms_router


@pytest.fixture(autouse=True)
def _isolated_whatsapp_bot_conversation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla el historial del bot de WhatsApp entre tests.

    El singleton `whatsapp_bot.conversation_store` usa el engine real de
    MySQL para sobrevivir a un restart en producción — sin esto, correr la
    suite dos veces filtraría estado (deal_id/historial) de una corrida de
    pytest a la siguiente. `ConversationStore()` sin `engine=` crea un
    SQLite en memoria aislado por instancia.

    `app.forms.router` importó el mismo singleton por nombre
    (`from app.flows.whatsapp_bot import conversation_store`), así que
    parchear el atributo de `whatsapp_bot` no le llega — necesita su propio
    `monkeypatch.setattr`, con la misma instancia para que ambos módulos
    vean el mismo estado dentro de un test.
    """
    store = whatsapp_bot.ConversationStore()
    monkeypatch.setattr(whatsapp_bot, "conversation_store", store)
    monkeypatch.setattr(forms_router, "conversation_store", store)
