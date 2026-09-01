from __future__ import annotations

import pytest

from app.flows import whatsapp_bot


@pytest.fixture(autouse=True)
def _isolated_whatsapp_bot_conversation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla el historial del bot de WhatsApp entre tests.

    El singleton `whatsapp_bot.conversation_store` usa el engine real de
    MySQL para sobrevivir a un restart en producción — sin esto, correr la
    suite dos veces filtraría estado (deal_id/historial) de una corrida de
    pytest a la siguiente. `ConversationStore()` sin `engine=` crea un
    SQLite en memoria aislado por instancia.
    """
    monkeypatch.setattr(whatsapp_bot, "conversation_store", whatsapp_bot.ConversationStore())
