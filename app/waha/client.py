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
        # Nombre `_http` (no `session`) porque `self.session` ya es el nombre de la
        # sesión de Waha (línea/número de WhatsApp) — evita conexión TCP/TLS nueva
        # en cada llamada, reutilizándola entre requests de la misma instancia.
        self._http = requests.Session()

    def is_reachable(self, session: str | None = None) -> bool:
        """Chequeo liviano de disponibilidad (ver GET /health/integrations en app/main.py).

        Llama a `GET /api/sessions/{session}` y confirma que el status sea
        "WORKING" — a diferencia de pegarle solo a `/api/version` (lo que
        hace el healthcheck de docker-compose.yml), esto detecta también el
        caso de que Waha esté arriba pero la sesión de WhatsApp se haya
        desconectado/deslogueado, que es la falla real que le importa a
        quien envía mensajes. Nunca lanza: loguea y devuelve False."""
        try:
            response = self._http.get(
                f"{self.base_url}/api/sessions/{session or self.session}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            return isinstance(payload, dict) and payload.get("status") == "WORKING"
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("Waha no está respondiendo (chequeo de disponibilidad): %s", exc)
            return False

    def mark_seen(self, chat_id: str, session: str | None = None) -> bool:
        """Marca como visto el último mensaje de un chat (`POST /api/sendSeen`). No lanza si falla.

        Parte de la simulación de comportamiento humano antes de responder
        (ver `send_text`/`send_voice`) — WhatsApp penaliza cuentas que
        contestan sin nunca "ver" el mensaje. Best-effort: un fallo acá no
        debe bloquear el envío real.
        """
        try:
            response = self._http.post(
                f"{self.base_url}/api/sendSeen",
                json={"chatId": chat_id, "session": session or self.session},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return True
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("Error marcando como visto el chat %s vía Waha: %s", chat_id, exc)
            return False

    def start_typing(self, chat_id: str, session: str | None = None) -> bool:
        """Activa el indicador "escribiendo..." en un chat (`POST /api/startTyping`). No lanza si falla."""
        try:
            response = self._http.post(
                f"{self.base_url}/api/startTyping",
                json={"chatId": chat_id, "session": session or self.session},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return True
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("Error activando 'escribiendo' en el chat %s vía Waha: %s", chat_id, exc)
            return False

    def stop_typing(self, chat_id: str, session: str | None = None) -> bool:
        """Desactiva el indicador "escribiendo..." en un chat (`POST /api/stopTyping`). No lanza si falla."""
        try:
            response = self._http.post(
                f"{self.base_url}/api/stopTyping",
                json={"chatId": chat_id, "session": session or self.session},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return True
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("Error desactivando 'escribiendo' en el chat %s vía Waha: %s", chat_id, exc)
            return False

    def _simulate_human_pacing(self, chat_id: str, session: str | None) -> None:
        """"Visto" + "escribiendo..." + pausa aleatoria 5-15s antes de un envío real.

        Mitigación de baneo de WhatsApp (ver docs/whatsapp-bot.md y el
        README, sección "Riesgo de baneo de Waha") — contestar
        instantáneo y sin nunca marcar visto/escribiendo es un patrón que
        WhatsApp asocia a bots de spam. Cada llamada a `send_text`/
        `send_voice` la corre por su cuenta, así que también sirve como
        pausa entre mensajes consecutivos de un mismo turno sin que cada
        flujo (`app/flows/*`) tenga que manejar el delay a mano.
        """
        self.mark_seen(chat_id, session)
        self.start_typing(chat_id, session)
        time.sleep(random.uniform(5.0, 15.0))
        self.stop_typing(chat_id, session)

    def send_text(
        self, chat_id: str, text: str, session: str | None = None, *, simulate_typing: bool = True
    ) -> bool:
        """Envía un mensaje de texto a un chat de WhatsApp. No lanza si falla.

        `chat_id` es el número en formato Waha, ej. "573001112233@c.us".
        `session` es el nombre de la sesión de Waha (línea/número) a usar —
        si no se pasa, se usa la de settings (WAHA_SESSION). Necesario
        cuando hay más de una sesión activa (ej. distintas líneas por
        pipeline de Bitrix) y no todos los mensajes deben salir por la
        misma. `simulate_typing=False` salta la pausa/"escribiendo" de
        `_simulate_human_pacing` (solo para el endpoint de scaffolding
        `/webhook/waha-test` y tests) — en producción siempre debe ir en
        True. Retorna True si Waha aceptó el envío, False en caso de error.
        """
        if simulate_typing:
            self._simulate_human_pacing(chat_id, session)
        try:
            response = self._http.post(
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

    def send_voice(
        self,
        chat_id: str,
        audio_base64: str,
        *,
        mimetype: str = "audio/ogg; codecs=opus",
        filename: str = "voice.ogg",
        session: str | None = None,
        simulate_typing: bool = True,
    ) -> bool:
        """Envía una nota de voz a un chat de WhatsApp. No lanza si falla.

        `audio_base64` va sin el prefijo `data:...;base64,` (solo el
        contenido codificado) — Waha lo espera así en `file.data`. Pensado
        para audios fijos ya conocidos en tiempo de build (ver
        `app.flows.whatsapp_bot_welcome`), no para reenviar audio recibido
        de un usuario. `simulate_typing` ver docstring de `send_text`.
        Retorna True si Waha aceptó el envío, False si falla.
        """
        if simulate_typing:
            self._simulate_human_pacing(chat_id, session)
        try:
            response = self._http.post(
                f"{self.base_url}/api/sendVoice",
                json={
                    "chatId": chat_id,
                    "file": {"mimetype": mimetype, "filename": filename, "data": audio_base64},
                    "session": session or self.session,
                },
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info("Nota de voz enviada a %s vía Waha", chat_id)
            return True
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error enviando nota de voz a %s vía Waha: %s", chat_id, exc)
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
            response = self._http.get(
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

    def get_chat_messages(
        self, chat_id: str, *, limit: int = 50, from_me: bool | None = None, session: str | None = None
    ) -> list[dict] | None:
        """Trae los últimos `limit` mensajes de un chat vía `GET /api/{session}/chats/{chatId}/messages`.

        Pensado para leer historial real de WhatsApp que el bot nunca vio
        (ej. un asesor humano ya habló con la persona por WhatsApp Web antes
        de que el bot existiera para ese chat, ver
        `app.flows.whatsapp_bot_history_seed.seed_history_from_waha`). Cada
        mensaje trae, entre otros campos, `fromMe` (bool) y `body` (texto) —
        mismo shape que el payload del webhook (`app.waha.inbound`). No
        lanza si falla ni si la respuesta no tiene la forma esperada,
        retorna `None` en ambos casos.

        `from_me`, si se pasa, filtra del lado de Waha (`filter.fromMe`) en
        vez de traer mensajes mezclados y filtrar acá — evita que mensajes
        consecutivos del otro lado empujen fuera de la ventana de `limit`
        al único mensaje del lado que en realidad se está buscando.
        """
        params: dict[str, int | str] = {"limit": limit}
        if from_me is not None:
            params["filter.fromMe"] = "true" if from_me else "false"
        try:
            response = self._http.get(
                f"{self.base_url}/api/{session or self.session}/chats/{chat_id}/messages",
                params=params,
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else None
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error obteniendo mensajes del chat %s vía Waha: %s", chat_id, exc)
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
            response = self._http.get(
                f"{self.base_url}{media_path}",
                headers=self._headers,
                timeout=MEDIA_DOWNLOAD_TIMEOUT,
            )
            response.raise_for_status()
            return response.content
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error descargando media (%s) vía Waha: %s", media_path, exc)
            return None

