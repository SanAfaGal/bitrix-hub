"""Cliente mínimo para generar respuestas de texto vía un LLM.

Usa el SDK de OpenAI apuntado a `LLM_BASE_URL` — funciona tal cual con
OpenAI y con cualquier otro proveedor que hable el mismo protocolo
(chat completions), que es la mayoría (Groq, Together, DeepSeek,
OpenRouter, Azure OpenAI, un modelo local servido con Ollama/vLLM, etc.).
"""
from __future__ import annotations

import logging

import openai

from app.llm.settings import LlmSettings

logger = logging.getLogger(__name__)

MAX_TOKENS = 500


class LlmClient:
    """Encapsula las llamadas al LLM. No lanza si falla."""

    def __init__(self, settings: LlmSettings) -> None:
        self.model = settings.model
        self._client = openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    def reply(self, system_prompt: str, history: list[dict[str, str]], user_text: str) -> str | None:
        """Genera una respuesta de texto dado un system prompt y el historial de turnos.

        `history` es una lista de `{"role": "user"|"assistant", "content": str}`,
        más viejo primero, sin incluir el turno actual. Retorna `None` si la
        llamada falla (red, rate limit, respuesta vacía) — quien llame decide
        el fallback (ej. no responder, o mandar un mensaje genérico).
        """
        messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_text}]
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=messages,
            )
        except openai.OpenAIError as exc:
            logger.error("Error llamando al LLM: %s", exc)
            return None

        if not response.choices:
            return None

        text = response.choices[0].message.content
        return text.strip() if text and text.strip() else None
