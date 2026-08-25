"""Configuración de variables de entorno para el cliente LLM.

Usa el SDK de OpenAI, pero no está atado a OpenAI: cualquier proveedor que
exponga una API compatible (Groq, Together, DeepSeek, OpenRouter, un modelo
propio servido con Ollama/vLLM, Azure OpenAI, etc.) sirve con solo cambiar
`LLM_BASE_URL` y `LLM_MODEL` — no hace falta tocar código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class LlmSettings:
    api_key: str
    model: str
    base_url: str | None


def load_llm_settings() -> LlmSettings:
    """Carga y valida la configuración del cliente LLM."""
    load_dotenv()

    api_key = (os.getenv("LLM_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Falta variable de entorno: LLM_API_KEY")

    model = (os.getenv("LLM_MODEL") or "").strip() or DEFAULT_MODEL
    base_url = (os.getenv("LLM_BASE_URL") or "").strip() or None

    return LlmSettings(api_key=api_key, model=model, base_url=base_url)
