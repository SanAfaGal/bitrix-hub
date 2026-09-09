from __future__ import annotations

import json

from app.flows.whatsapp_bot_llm import analyze_prior_history


class FakeLlmClient:
    def __init__(self, reply_text: str | None) -> None:
        self.reply_text = reply_text
        self.calls: list[tuple[str, list[dict], str]] = []

    def reply(self, system_prompt: str, history: list[dict], user_text: str) -> str | None:
        self.calls.append((system_prompt, history, user_text))
        return self.reply_text


_VALID_ANALYSIS = {
    "client_full_name": "Carlos Ramírez",
    "client_phone": "573001112233",
    "process_explained": True,
    "authorization_mentioned": False,
    "summary": "El asesor saludó y le explicó el proceso al cliente.",
}

_MESSAGES = [
    {"id": "1", "fromMe": False, "body": "hola, quiero vender mi apto", "timestamp": 100},
    {"id": "2", "fromMe": True, "body": "claro, le explico cómo funciona el proceso", "timestamp": 101},
]


def test_analyze_prior_history_parses_valid_llm_json() -> None:
    llm = FakeLlmClient(json.dumps(_VALID_ANALYSIS))

    result = analyze_prior_history(llm, _MESSAGES)

    assert result == _VALID_ANALYSIS
    # Se manda como user_text con history vacío — una sola pasada, no una conversación.
    assert len(llm.calls) == 1
    system_prompt, history, transcript = llm.calls[0]
    assert history == []
    assert "Cliente: hola, quiero vender mi apto" in transcript
    assert "Asesor: claro, le explico cómo funciona el proceso" in transcript
    # Orden cronológico por timestamp, aunque llegaran desordenados.
    assert transcript.index("Cliente:") < transcript.index("Asesor:")


def test_analyze_prior_history_orders_messages_chronologically_even_if_out_of_order() -> None:
    llm = FakeLlmClient(json.dumps(_VALID_ANALYSIS))
    shuffled = [_MESSAGES[1], _MESSAGES[0]]

    analyze_prior_history(llm, shuffled)

    transcript = llm.calls[0][2]
    assert transcript.index("Cliente:") < transcript.index("Asesor:")


def test_analyze_prior_history_returns_safe_default_on_garbage_llm_response() -> None:
    llm = FakeLlmClient("esto no es json")

    result = analyze_prior_history(llm, _MESSAGES)

    assert result == {
        "client_full_name": None,
        "client_phone": None,
        "process_explained": False,
        "authorization_mentioned": False,
        "summary": "",
    }


def test_analyze_prior_history_returns_safe_default_on_missing_fields() -> None:
    llm = FakeLlmClient(json.dumps({"summary": "algo"}))

    result = analyze_prior_history(llm, _MESSAGES)

    assert result["client_full_name"] is None
    assert result["client_phone"] is None
    assert result["process_explained"] is False
    assert result["authorization_mentioned"] is False
    assert result["summary"] == "algo"


def test_analyze_prior_history_returns_safe_default_when_llm_fails() -> None:
    llm = FakeLlmClient(None)

    result = analyze_prior_history(llm, _MESSAGES)

    assert result == {
        "client_full_name": None,
        "client_phone": None,
        "process_explained": False,
        "authorization_mentioned": False,
        "summary": "",
    }


def test_analyze_prior_history_with_empty_messages_skips_llm_call() -> None:
    """Sin texto que analizar (lista vacía, o solo mensajes de media sin body), se retorna el
    default seguro directamente sin pegarle al LLM — no hay nada que preguntarle."""
    llm = FakeLlmClient(json.dumps(_VALID_ANALYSIS))

    result = analyze_prior_history(llm, [])

    assert result == {
        "client_full_name": None,
        "client_phone": None,
        "process_explained": False,
        "authorization_mentioned": False,
        "summary": "",
    }
    assert llm.calls == []


def test_analyze_prior_history_skips_messages_without_text_body() -> None:
    llm = FakeLlmClient(json.dumps(_VALID_ANALYSIS))
    messages = [{"id": "1", "fromMe": False, "hasMedia": True, "body": "", "timestamp": 100}]

    analyze_prior_history(llm, messages)

    assert llm.calls == []
