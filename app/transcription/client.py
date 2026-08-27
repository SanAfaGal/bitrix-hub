"""Cliente HTTP mínimo para el servicio de transcripción de audio (whisper-asr-webservice)."""
from __future__ import annotations

import logging
import threading
import time

import requests

from app.transcription.settings import TranscriptionSettings

logger = logging.getLogger(__name__)

# Inferencia en CPU es lenta comparada con una llamada REST típica — una nota
# de voz de WhatsApp puede tardar varios segundos en transcribirse.
REQUEST_TIMEOUT = 60

# Notas de voz de WhatsApp normalmente pesan pocos MB — un archivo más
# pesado que esto no vale la espera de REQUEST_TIMEOUT completo en CPU, se
# rechaza de una vez.
MAX_AUDIO_BYTES = 15 * 1024 * 1024

# Tras un fallo de red/HTTP contra whisper, no se reintenta por este rato —
# evita que cada mensaje de una ráfaga espere el timeout completo mientras
# el servicio está caído. Compartido entre instancias (get_transcription_client()
# crea un TranscriptionClient nuevo por request) vía estado a nivel de módulo.
COOLDOWN_SECONDS = 30

_lock = threading.Lock()
_unavailable_until = 0.0


def _mark_unavailable() -> None:
    global _unavailable_until
    with _lock:
        _unavailable_until = time.monotonic() + COOLDOWN_SECONDS


def _is_in_cooldown() -> bool:
    with _lock:
        return time.monotonic() < _unavailable_until


def reset_circuit() -> None:
    """Solo para tests: limpia el estado de "whisper caído" entre casos."""
    global _unavailable_until
    with _lock:
        _unavailable_until = 0.0


class TranscriptionClient:
    """Encapsula las llamadas al servicio de transcripción (whisper-asr-webservice)."""

    def __init__(self, settings: TranscriptionSettings) -> None:
        self.base_url = settings.base_url.rstrip("/")
        self.language = settings.language

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str | None:
        """Transcribe un audio a texto. No lanza si falla.

        Retorna `None` si el audio supera `MAX_AUDIO_BYTES`, si whisper está
        en cooldown por un fallo reciente, si el servicio falla/responde con
        error, o si no reconoce voz (texto vacío).
        """
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            logger.warning(
                "Audio de %d bytes supera el límite (%d), no se transcribe", len(audio_bytes), MAX_AUDIO_BYTES
            )
            return None

        if _is_in_cooldown():
            logger.warning("Whisper en cooldown por un fallo reciente, no se reintenta todavía")
            return None

        try:
            params: dict[str, str] = {"output": "text"}
            if self.language:
                params["language"] = self.language
            response = requests.post(
                f"{self.base_url}/asr",
                params=params,
                files={"audio_file": (filename, audio_bytes)},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            text = response.text.strip()
            return text or None
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Error transcribiendo audio vía whisper: %s", exc)
            _mark_unavailable()
            return None
