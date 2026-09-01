"""Cliente mínimo para generar respuestas de texto vía un LLM.

Usa el SDK de OpenAI apuntado a `LLM_BASE_URL` — funciona tal cual con
OpenAI y con cualquier otro proveedor que hable el mismo protocolo
(chat completions), que es la mayoría (Groq, Together, DeepSeek,
OpenRouter, Azure OpenAI, un modelo local servido con Ollama/vLLM, etc.).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import openai

from app.llm.settings import LlmSettings

logger = logging.getLogger(__name__)

MAX_TOKENS = 250

# Los modelos actuales de OpenAI (probado con gpt-4.1-nano y gpt-5-nano, no
# solo la familia "reasoning" o1/o3/o4) rechazan `max_tokens` en Chat
# Completions y piden `max_completion_tokens` en su lugar. Además gastan
# parte del presupuesto en tokens de "razonamiento" oculto antes de la
# respuesta visible — con MAX_TOKENS=250 eso alcanzaba a consumir todo el
# presupuesto sin dejar nada para el texto (finish_reason "length", content
# vacío). `reasoning_effort="minimal"` corta ese gasto, apropiado para este
# bot (respuestas cortas). No hay forma confiable de adivinar esto por
# nombre de modelo (la lista de familias cambia todo el tiempo) — se decide
# por si se habla directo con OpenAI (`base_url` vacío) o con un proveedor
# compatible con endpoint propio (Groq, Ollama, etc.), que puede no soportar
# ninguno de los dos parámetros nuevos todavía.
def _completion_kwargs(base_url: str | None) -> dict[str, int | str]:
    if base_url is None:
        return {"max_completion_tokens": MAX_TOKENS, "reasoning_effort": "minimal"}
    return {"max_tokens": MAX_TOKENS}

# Pricing per 1K tokens (OpenAI gpt-4o-mini; adjust for other models)
MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "mixtral-8x7b-32768": {"input": 0.00027, "output": 0.00081},  # Groq fallback
}


@dataclass
class LlmResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float | None = None


class LlmClient:
    """Encapsula las llamadas al LLM. No lanza si falla."""

    def __init__(self, settings: LlmSettings) -> None:
        self.model = settings.model
        self._api_key = settings.api_key
        self._base_url = settings.base_url
        self.fallback_model = settings.fallback_model
        self._fallback_base_url = settings.fallback_base_url
        self._fallback_api_key = settings.fallback_api_key
        self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)

    def reply(self, system_prompt: str, history: list[dict[str, str]], user_text: str) -> str | None:
        """Genera una respuesta de texto dado un system prompt y el historial de turnos.

        `history` es una lista de `{"role": "user"|"assistant", "content": str}`,
        más viejo primero, sin incluir el turno actual. Retorna `None` si la
        llamada falla (red, rate limit, respuesta vacía) — quien llame decide
        el fallback (ej. no responder, o mandar un mensaje genérico).
        """
        response = self._call_llm(self.model, system_prompt, history, user_text)

        if response is None and self.fallback_model:
            logger.warning("Primary model %s failed, trying fallback %s", self.model, self.fallback_model)
            response = self._call_llm(self.fallback_model, system_prompt, history, user_text, fallback=True)

        if response is None:
            return None

        if response.cost_usd is not None:
            logger.info(
                "LLM %s: %d input, %d output tokens, cost: $%.6f",
                response.model,
                response.input_tokens,
                response.output_tokens,
                response.cost_usd,
            )

        return response.text

    def _call_llm(
        self, model: str, system_prompt: str, history: list[dict[str, str]], user_text: str, fallback: bool = False
    ) -> LlmResponse | None:
        """Llama al LLM. Si `fallback=True`, usa base_url del fallback."""
        messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_text}]

        try:
            if fallback and self._fallback_base_url:
                client = openai.OpenAI(
                    api_key=self._fallback_api_key or self._api_key, base_url=self._fallback_base_url
                )
                base_url = self._fallback_base_url
            else:
                client = self._client
                base_url = self._base_url

            kwargs = _completion_kwargs(base_url)
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, response_format={"type": "json_object"}, **kwargs
                )
            except openai.BadRequestError as exc:
                # No todo modelo accesible directo por OpenAI es de la familia "reasoning"
                # (ver `_completion_kwargs`) — gpt-4.1-nano, por ejemplo, rechaza
                # `reasoning_effort` aunque se hable con OpenAI sin base_url custom.
                # Se reintenta sin el parámetro en vez de adivinar por nombre de modelo.
                if "reasoning_effort" in kwargs and "reasoning_effort" in str(exc):
                    logger.warning("Modelo %s no soporta reasoning_effort, reintentando sin ese parámetro", model)
                    kwargs.pop("reasoning_effort")
                    response = client.chat.completions.create(
                        model=model, messages=messages, response_format={"type": "json_object"}, **kwargs
                    )
                else:
                    raise
        except openai.OpenAIError as exc:
            logger.error("Error LLM %s: %s", model, exc)
            return None

        if not response.choices:
            logger.warning("LLM %s returned no choices", model)
            return None

        text = response.choices[0].message.content
        if not text or not text.strip():
            return None

        input_tokens = getattr(response.usage, "prompt_tokens", 0) if response.usage else 0
        output_tokens = getattr(response.usage, "completion_tokens", 0) if response.usage else 0

        cost = self._estimate_cost(model, input_tokens, output_tokens)

        return LlmResponse(
            text=text.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            cost_usd=cost,
        )

    @staticmethod
    def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
        """Estima costo basado en modelo y tokens (aproximado)."""
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            return None
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000
