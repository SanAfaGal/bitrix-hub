"""Cap de frecuencia para mensajes de WhatsApp que el hub inicia sin respuesta previa del contacto.

Mitigación de baneo (ver docs/whatsapp-bot.md y README, sección "Riesgo de
baneo de Waha"): WAHA recomienda no más de unos pocos mensajes por hora a un
contacto que todavía no te ha escrito — pasado ese punto se asume que ya hay
una conversación activa y no tiene sentido seguir limitando (cortaría el
producto). Por eso el cap acá solo aplica a los tres flujos que mandan el
primer mensaje sin que el contacto haya escrito antes
(`app.flows.welcome_authorization`, `app.flows.notify_contact`,
`app.flows.brokerage_authorization_signed`) — el bot reactivo
(`app.flows.whatsapp_bot`) siempre responde a un mensaje entrante y no pasa
por acá.

Mismo idioma que `app.shared.rate_limit` y el rate limit por chat de
`ConversationStore`: ventana deslizante en memoria, dict de deques + Lock.
No sobrevive un restart ni se comparte entre réplicas — igual que esos, para
un solo contenedor alcanza.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock

from app.waha.client import WahaClient

logger = logging.getLogger(__name__)

# Recomendación de WAHA para contactos que todavía no respondieron.
_PROACTIVE_MAX_PER_HOUR = 4
_PROACTIVE_WINDOW_SECONDS = 3600.0

# Historial suficiente para detectar una respuesta real del contacto sin
# traer la conversación completa — mismo criterio que
# `whatsapp_bot_new_chat_check._NEW_CHAT_HISTORY_CHECK_LIMIT`, con más
# margen porque acá no hay un `message_id` puntual que descartar.
_REPLY_CHECK_HISTORY_LIMIT = 50

_lock = Lock()
_sent_at: dict[str, deque[float]] = defaultdict(deque)


def has_contact_replied(chat_id: str, waha_client: WahaClient, session: str | None = None) -> bool:
    """True si en el historial de Waha hay al menos un mensaje real del contacto (no del hub).

    Si la consulta a Waha falla (`None`), falla cerrado: se asume que NO ha
    respondido todavía — más seguro aplicar el cap de más que arriesgar un
    envío sin límite por no poder verificarlo.
    """
    messages = waha_client.get_chat_messages(chat_id, limit=_REPLY_CHECK_HISTORY_LIMIT, session=session)
    if messages is None:
        return False
    return any(not m.get("fromMe") and m.get("body") for m in messages)


def should_throttle_proactive_send(chat_id: str, waha_client: WahaClient, session: str | None = None) -> bool:
    """True si este envío hay que bloquearlo por el cap de frecuencia (llamar ANTES de mandar).

    No limita nada una vez el contacto ya respondió alguna vez — ver
    docstring del módulo. Mientras no haya respondido, registra el intento
    en la ventana deslizante y bloquea si ya se pasó de
    `_PROACTIVE_MAX_PER_HOUR` en la última hora.
    """
    if has_contact_replied(chat_id, waha_client, session):
        return False

    now = time.monotonic()
    with _lock:
        sent_at = _sent_at[chat_id]
        while sent_at and now - sent_at[0] > _PROACTIVE_WINDOW_SECONDS:
            sent_at.popleft()
        if len(sent_at) >= _PROACTIVE_MAX_PER_HOUR:
            logger.warning(
                "Cap de frecuencia anti-baneo alcanzado para %s (%d mensajes en la última hora), envío bloqueado",
                chat_id,
                len(sent_at),
            )
            return True
        sent_at.append(now)
        return False
