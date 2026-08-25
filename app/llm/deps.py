"""Dependencias de FastAPI para el cliente LLM."""
from __future__ import annotations

from fastapi import HTTPException

from app.llm.client import LlmClient
from app.llm.settings import load_llm_settings


def get_llm_client() -> LlmClient:
    """Crea un cliente LLM a partir de la configuración de entorno."""
    try:
        settings = load_llm_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LlmClient(settings)
