"""Parseo de eventos entrantes de Waha (webhook `message`).

Waha manda el mismo shape de payload sin importar el engine (GOWS, etc.):
`{"event": "message", "session": "...", "payload": {"id": ..., "from": ...,
"fromMe": ..., "body": ..., "hasMedia": ...}}`. Este módulo solo extrae lo
que el bot necesita — no valida más allá de eso.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Nombre para mostrar del remitente (perfil de WhatsApp) — best-effort: la
# documentación de Waha no fija un nombre de campo estable para esto (vive
# dentro de `_data`, "datos internos del engine, puede variar según el
# engine" según sus propias docs). Se prueban las rutas más probables según
# los engines soportados (WEBJS/NOWEB usan notifyName/pushName estilo
# whatsapp-web.js/Baileys; GOWS es un wrapper de whatsmeow, que expone
# Info.PushName) — si ninguna aplica, se sigue sin nombre (no es crítico,
# solo mejora el nombre con el que se crea el contacto en Bitrix).
_SENDER_NAME_PATHS: tuple[tuple[str, ...], ...] = (
    ("notifyName",),
    ("_data", "notifyName"),
    ("_data", "pushName"),
    ("_data", "Info", "PushName"),
)


def _dig(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _extract_sender_name(payload: dict[str, Any]) -> str | None:
    for path in _SENDER_NAME_PATHS:
        value = _dig(payload, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@dataclass(frozen=True)
class InboundMessage:
    chat_id: str
    text: str
    message_id: str
    session: str
    sender_name: str | None = None


def parse_inbound_message(event: dict[str, Any]) -> InboundMessage | None:
    """Extrae un mensaje de texto entrante del payload de webhook de Waha.

    Retorna `None` (sin lanzar) cuando el evento no aplica: no es de tipo
    `message`, es eco de un mensaje mandado por el propio bot (`fromMe`),
    trae media en vez de texto, o le faltan campos mínimos.
    """
    if event.get("event") != "message":
        return None

    payload = event.get("payload") or {}
    if payload.get("fromMe"):
        return None

    if payload.get("hasMedia"):
        logger.info("Mensaje entrante con media (sin soporte todavía), ignorado: %s", payload.get("id"))
        return None

    chat_id = payload.get("from")
    text = payload.get("body")
    message_id = payload.get("id")
    session = event.get("session")

    if not chat_id or not text or not message_id or not session:
        logger.warning("Evento de Waha incompleto, ignorado: %s", event)
        return None

    if not isinstance(text, str) or not text.strip():
        return None

    return InboundMessage(
        chat_id=chat_id,
        text=text.strip(),
        message_id=str(message_id),
        session=session,
        sender_name=_extract_sender_name(payload),
    )
