"""Cliente HTTP mínimo para la REST API de Waha (WhatsApp HTTP API)."""
from __future__ import annotations

import logging
import random
import time

import requests

from app.waha.settings import WahaSettings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

# Descargar un audio de nota de voz puede pesar varios MB — más margen que
# REQUEST_TIMEOUT.
MEDIA_DOWNLOAD_TIMEOUT = 30


class WahaClient:
    """Encapsula las llamadas a la REST API de Waha."""

    def __init__(self, settings: WahaSettings) -> None:
        self.base_url = settings.base_url.rstrip("/")
        self.session = settings.session
        self._headers = {"X-Api-Key": settings.api_key} if settings.api_key else {}

    def send_text(self, chat_id: str, text: str, session: str | None = None) -> bool:
        """Envía un mensaje de texto a un chat de WhatsApp. No lanza si falla.

        `chat_id` es el número en formato Waha, ej. "573001112233@c.us".
        `session` es el nombre de la sesión de Waha (línea/número) a usar —
        si no se pasa, se usa la de settings (WAHA_SESSION). Necesario
        cuando hay más de una sesión activa (ej. distintas líneas por
        pipeline de Bitrix) y no todos los mensajes deben salir por la
        misma. Retorna True si Waha aceptó el envío, False en caso de error.
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/sendText",
                json={"chatId": chat_id, "text": text, "session": session or self.session},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info("Mensaje enviado a %s vía Waha", chat_id)
            return True
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error enviando mensaje a %s vía Waha: %s", chat_id, exc)
            return False

    def resolve_lid_to_phone(self, lid: str, session: str | None = None) -> str | None:
        """Resuelve un identificador `@lid` (número oculto) al chatId real, si Waha ya lo conoce.

        `lid` va sin el sufijo `@lid` (solo el identificador, ver
        `app.waha.phone.lid_from_chat_id`). Usa `GET /api/{session}/lids/{lid}`
        — Waha mapea LID a número real (`pn`) cuando ya lo aprendió
        (comparten grupo, chat directo previo, etc.); si no hay mapeo
        todavía responde 200 con `"pn": null` (no 404). Retorna el chatId
        (`"<teléfono>@c.us"`) si hay mapeo, o `None` si no hay o falla la
        llamada.
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/{session or self.session}/lids/{lid}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            pn = payload.get("pn") if isinstance(payload, dict) else None
            return pn if isinstance(pn, str) and pn else None
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error resolviendo lid %s vía Waha: %s", lid, exc)
            return None

    def download_media(self, media_path: str) -> bytes | None:
        """Descarga un archivo multimedia (ej. audio de una nota de voz) ya resuelto por Waha.

        `media_path` es el path (sin host) de `payload.media.url` del propio
        mensaje entrante (ver `app.waha.inbound._media_path`) — se pide sobre
        `WAHA_BASE_URL` (alcanzable desde este contenedor) en vez de la URL
        absoluta del payload, que usa `WAHA_PUBLIC_URL` y puede no resolver
        desde acá. No lanza si falla, retorna `None`.
        """
        try:
            response = requests.get(
                f"{self.base_url}{media_path}",
                headers=self._headers,
                timeout=MEDIA_DOWNLOAD_TIMEOUT,
            )
            response.raise_for_status()
            return response.content
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error descargando media (%s) vía Waha: %s", media_path, exc)
            return None

    def send_text_sequence(
        self,
        chat_id: str,
        messages: list[str],
        *,
        session: str | None = None,
        min_delay: float = 3.0,
        max_delay: float = 6.0,
    ) -> bool:
        """Envía varios mensajes al mismo chat, con pausa aleatoria entre cada uno.

        Simula el ritmo de una respuesta humana en vez de mandar todo de
        golpe. Método síncrono (bloquea con `time.sleep` durante la pausa) —
        quien lo llame desde una ruta async debe correrlo en un hilo aparte
        (`asyncio.to_thread`) para no congelar el event loop. Retorna True
        solo si Waha aceptó todos los mensajes.
        """
        all_sent = True
        for index, text in enumerate(messages):
            sent = self.send_text(chat_id, text, session=session)
            all_sent = all_sent and sent
            if index < len(messages) - 1:
                time.sleep(random.uniform(min_delay, max_delay))
        return all_sent
