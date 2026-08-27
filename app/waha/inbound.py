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
from urllib.parse import urlparse

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


# Confirmado contra el schema WAMessage/WAMedia de la API de Waha (mismo
# shape que trae el webhook `message`): un mensaje con media trae
# `payload.media = {"url": ..., "mimetype": ..., ...}` cuando Waha ya lo
# descargó. `url` es absoluta (usa WAHA_PUBLIC_URL, ej.
# "http://localhost:3000/api/files/xxx.oga") — para pedirla desde este
# contenedor hay que descartar host/esquema y pegarle al path sobre
# WAHA_BASE_URL (ver WahaClient.download_media), porque WAHA_PUBLIC_URL no
# necesariamente resuelve desde acá.
_AUDIO_MIMETYPE_PREFIX = "audio/"


def _is_audio_media(media: Any) -> bool:
    if not isinstance(media, dict):
        return False
    mimetype = media.get("mimetype")
    return isinstance(mimetype, str) and mimetype.lower().startswith(_AUDIO_MIMETYPE_PREFIX)


def _media_path(media: dict[str, Any]) -> str | None:
    """Path (sin host) del archivo ya descargado por Waha, o `None` si Waha
    no lo pudo descargar todavía (`media.error`) — en ese caso queda sin `url`.
    """
    url = media.get("url")
    if not isinstance(url, str) or not url:
        return None
    return urlparse(url).path


@dataclass(frozen=True)
class InboundMessage:
    chat_id: str
    text: str
    message_id: str
    session: str
    sender_name: str | None = None
    is_audio: bool = False
    audio_media_path: str | None = None


def parse_inbound_message(event: dict[str, Any]) -> InboundMessage | None:
    """Extrae un mensaje de texto entrante del payload de webhook de Waha.

    Retorna `None` (sin lanzar) cuando el evento no aplica: no es de tipo
    `message`, es eco de un mensaje mandado por el propio bot (`fromMe`),
    trae media no soportada (imagen, video, documento), o le faltan campos
    mínimos. Los mensajes de audio (notas de voz) sí se dejan pasar, con
    `text=""` e `is_audio=True` — el texto se completa transcribiendo el
    audio río abajo (ver `app/flows/whatsapp_bot.py`).
    """
    if event.get("event") != "message":
        return None

    payload = event.get("payload") or {}
    if payload.get("fromMe"):
        return None

    # Actualizaciones de "Estado" de WhatsApp de los contactos (no un chat
    # real) — llegan a cada rato como evento "message", inundarían el log si
    # se trataran igual que un mensaje con media sin soporte.
    if payload.get("from") == "status@broadcast":
        return None

    media = payload.get("media")
    is_audio = bool(payload.get("hasMedia")) and _is_audio_media(media)

    if payload.get("hasMedia") and not is_audio:
        logger.info("Mensaje entrante con media no soportada, ignorado: %s", payload.get("id"))
        return None

    chat_id = payload.get("from")
    text = payload.get("body")
    message_id = payload.get("id")
    session = event.get("session")

    if not chat_id or not message_id or not session:
        logger.warning("Evento de Waha incompleto, ignorado: %s", event)
        return None

    if is_audio:
        return InboundMessage(
            chat_id=chat_id,
            text="",
            message_id=str(message_id),
            session=session,
            sender_name=_extract_sender_name(payload),
            is_audio=True,
            audio_media_path=_media_path(media),
        )

    if not text:
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
