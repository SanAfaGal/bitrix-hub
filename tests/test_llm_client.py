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
class FakeCompletion:
    choices: list[FakeChoice]


def _settings(**overrides: object) -> LlmSettings:
    base = {"api_key": "test-key", "model": "gpt-4o-mini", "base_url": None}
    base.update(overrides)
    return LlmSettings(**base)


def test_reply_returns_text_and_sends_expected_request(monkeypatch) -> None:
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeCompletion(choices=[FakeChoice(message=FakeMessage(content="hola, en que te ayudo?"))])

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


def test_reply_uses_custom_base_url_when_configured() -> None:
    client = LlmClient(_settings(base_url="http://localhost:11434/v1"))

    assert str(client._client.base_url) == "http://localhost:11434/v1/"


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
