from __future__ import annotations

import pytest
import requests

from app.transcription.client import MAX_AUDIO_BYTES, TranscriptionClient, reset_circuit
from app.transcription.settings import TranscriptionSettings


@pytest.fixture(autouse=True)
def _clean_circuit_state():
    reset_circuit()
    yield
    reset_circuit()


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")


def test_transcribe_posts_audio_and_returns_text(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, params: dict, files: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["files"] = files
        return FakeResponse(text="hola, quiero vender mi apartamento")

    monkeypatch.setattr("app.transcription.client.requests.post", fake_post)

    settings = TranscriptionSettings(base_url="http://localhost:9000", language="es")
    client = TranscriptionClient(settings)

    result = client.transcribe(b"audio-bytes", filename="nota.ogg")

    assert result == "hola, quiero vender mi apartamento"
    assert captured["url"] == "http://localhost:9000/asr"
    assert captured["params"] == {"output": "text", "language": "es"}
    assert captured["files"] == {"audio_file": ("nota.ogg", b"audio-bytes")}


def test_transcribe_omits_language_param_when_not_set(monkeypatch) -> None:
    captured = {}

    def fake_post(url: str, params: dict, files: dict, timeout: int) -> FakeResponse:
        captured["params"] = params
        return FakeResponse(text="hola")

    monkeypatch.setattr("app.transcription.client.requests.post", fake_post)

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)
    client.transcribe(b"audio-bytes")

    assert captured["params"] == {"output": "text"}


def test_transcribe_returns_none_on_request_error(monkeypatch) -> None:
    def fake_post(url: str, params: dict, files: dict, timeout: int) -> FakeResponse:
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.transcription.client.requests.post", fake_post)

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)

    assert client.transcribe(b"audio-bytes") is None


def test_transcribe_returns_none_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.transcription.client.requests.post", lambda url, params, files, timeout: FakeResponse(status_code=500)
    )

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)

    assert client.transcribe(b"audio-bytes") is None


def test_transcribe_returns_none_on_empty_text(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.transcription.client.requests.post",
        lambda url, params, files, timeout: FakeResponse(text="   "),
    )

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)

    assert client.transcribe(b"audio-bytes") is None


def test_transcribe_rejects_audio_over_size_limit_without_calling_whisper(monkeypatch) -> None:
    called = False

    def fake_post(*args, **kwargs) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse(text="no debería llegar acá")

    monkeypatch.setattr("app.transcription.client.requests.post", fake_post)

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)

    oversized_audio = b"0" * (MAX_AUDIO_BYTES + 1)
    assert client.transcribe(oversized_audio) is None
    assert called is False


def test_transcribe_enters_cooldown_after_request_error_and_skips_next_call(monkeypatch) -> None:
    call_count = 0

    def fake_post(url: str, params: dict, files: dict, timeout: int) -> FakeResponse:
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.transcription.client.requests.post", fake_post)

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)

    assert client.transcribe(b"audio-bytes") is None
    assert call_count == 1

    # Segundo intento inmediato: no debería ni golpear la red, sigue en cooldown.
    assert client.transcribe(b"audio-bytes") is None
    assert call_count == 1


def test_transcribe_does_not_enter_cooldown_on_empty_text(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.transcription.client.requests.post",
        lambda url, params, files, timeout: FakeResponse(text=""),
    )

    settings = TranscriptionSettings(base_url="http://localhost:9000", language=None)
    client = TranscriptionClient(settings)

    client.transcribe(b"audio-bytes")

    monkeypatch.setattr(
        "app.transcription.client.requests.post",
        lambda url, params, files, timeout: FakeResponse(text="ahora si hay texto"),
    )
    assert client.transcribe(b"audio-bytes") == "ahora si hay texto"
