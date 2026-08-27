"""Configuración de variables de entorno para el servicio de transcripción de audio."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class TranscriptionSettings:
    base_url: str
    language: str | None


def load_transcription_settings() -> TranscriptionSettings:
    """Carga y valida la configuración del servicio de transcripción."""
    load_dotenv()

    base_url = (os.getenv("TRANSCRIPTION_BASE_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Falta variable de entorno: TRANSCRIPTION_BASE_URL")

    language = (os.getenv("TRANSCRIPTION_LANGUAGE") or "").strip() or None

    return TranscriptionSettings(base_url=base_url, language=language)
