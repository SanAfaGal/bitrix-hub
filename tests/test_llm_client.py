from __future__ import annotations

from dataclasses import dataclass

import openai

from app.llm.client import LlmClient
from app.llm.settings import LlmSettings


@dataclass
class FakeMessage:
    content: str | None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]
    usage: FakeUsage | None = None


def _settings(**overrides: object) -> LlmSettings:
    base = {"api_key": "test-key", "model": "gpt-4o-mini", "base_url": None}
    base.update(overrides)
    return LlmSettings(**base)


def test_reply_returns_text_and_sends_expected_request(monkeypatch) -> None:
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeCompletion(
            choices=[FakeChoice(message=FakeMessage(content="hola, en que te ayudo?"))],
            usage=FakeUsage(prompt_tokens=50, completion_tokens=20),
        )

    client = LlmClient(_settings())
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hola! como te ayudo?"}]
    result = client.reply("system prompt", history, "tienen apartamentos?")

    assert result == "hola, en que te ayudo?"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["messages"] == [
        {"role": "system", "content": "system prompt"},
        *history,
        {"role": "user", "content": "tienen apartamentos?"},
    ]
    assert captured["response_format"] == {"type": "json_object"}


def test_reply_uses_max_completion_tokens_and_reasoning_effort_against_openai_directly(monkeypatch) -> None:
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeCompletion(choices=[FakeChoice(message=FakeMessage(content="ok"))])

    client = LlmClient(_settings(base_url=None))
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    client.reply("system", [], "hola")

    assert captured["max_completion_tokens"] == 250
    assert captured["reasoning_effort"] == "minimal"
    assert "max_tokens" not in captured


def test_reply_uses_plain_max_tokens_for_custom_base_url(monkeypatch) -> None:
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeCompletion(choices=[FakeChoice(message=FakeMessage(content="ok"))])

    client = LlmClient(_settings(base_url="http://localhost:11434/v1"))
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    client.reply("system", [], "hola")

    assert captured["max_tokens"] == 250
    assert "max_completion_tokens" not in captured
    assert "reasoning_effort" not in captured


def test_reply_uses_custom_base_url_when_configured() -> None:
    client = LlmClient(_settings(base_url="http://localhost:11434/v1"))

    assert str(client._client.base_url) == "http://localhost:11434/v1/"


def test_reply_falls_back_to_secondary_model_using_fallback_api_key(monkeypatch) -> None:
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "gpt-4o-mini":
            raise openai.APIError("boom", request=None, body=None)
        return FakeCompletion(choices=[FakeChoice(message=FakeMessage(content="respuesta del fallback"))])

    captured_clients: list[openai.OpenAI] = []
    original_openai_client = openai.OpenAI

    def spying_openai(*args, **kwargs):
        client = original_openai_client(*args, **kwargs)
        captured_clients.append(client)
        monkeypatch.setattr(client.chat.completions, "create", fake_create)
        return client

    monkeypatch.setattr("app.llm.client.openai.OpenAI", spying_openai)

    client = LlmClient(
        _settings(
            fallback_model="mixtral-8x7b-32768",
            fallback_base_url="https://api.groq.com/openai/v1",
            fallback_api_key="groq-key",
        )
    )

    result = client.reply("system", [], "hola")

    assert result == "respuesta del fallback"
    assert calls == ["gpt-4o-mini", "mixtral-8x7b-32768"]
    assert captured_clients[-1].api_key == "groq-key"


def test_reply_returns_none_on_api_error(monkeypatch) -> None:
    def fake_create(**kwargs):
        raise openai.APIError("boom", request=None, body=None)

    client = LlmClient(_settings())
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    assert client.reply("system", [], "hola") is None


def test_reply_returns_none_when_response_has_no_choices(monkeypatch) -> None:
    def fake_create(**kwargs):
        return FakeCompletion(choices=[])

    client = LlmClient(_settings())
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    assert client.reply("system", [], "hola") is None


def test_reply_returns_none_when_content_is_empty(monkeypatch) -> None:
    def fake_create(**kwargs):
        return FakeCompletion(choices=[FakeChoice(message=FakeMessage(content="   "))])

    client = LlmClient(_settings())
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    assert client.reply("system", [], "hola") is None
