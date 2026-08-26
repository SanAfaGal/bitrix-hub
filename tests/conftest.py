from __future__ import annotations

import pytest

from app.flows import whatsapp_bot


@pytest.fixture(autouse=True)
def _isolated_whatsapp_bot_conversation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla el historial del bot de WhatsApp entre tests.

    El singleton `whatsapp_bot.conversation_store` usa un archivo SQLite
    real (`WHATSAPP_BOT_DB_PATH`) para sobrevivir a un restart en
    producción — sin esto, correr la suite dos veces filtraría estado
    (deal_id/historial) de una corrida de pytest a la siguiente.
    """
    monkeypatch.setattr(whatsapp_bot, "conversation_store", whatsapp_bot.ConversationStore())
