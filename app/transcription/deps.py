"""Dependencias de FastAPI para el servicio de transcripción de audio."""
from __future__ import annotations

from fastapi import HTTPException

from app.transcription.client import TranscriptionClient
from app.transcription.settings import load_transcription_settings


def get_transcription_client() -> TranscriptionClient:
    """Crea un cliente de transcripción a partir de la configuración de entorno."""
    try:
        settings = load_transcription_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TranscriptionClient(settings)
