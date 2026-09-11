from __future__ import annotations

import pytest

from app.shared import idempotency


@pytest.fixture(autouse=True)
def _reset_used_tokens() -> None:
    idempotency._used_tokens.clear()


def test_new_token_is_unique() -> None:
    assert idempotency.new_token() != idempotency.new_token()


def test_consume_returns_true_the_first_time() -> None:
    token = idempotency.new_token()
    assert idempotency.consume(token) is True


def test_consume_returns_false_on_second_use() -> None:
    token = idempotency.new_token()
    idempotency.consume(token)

    assert idempotency.consume(token) is False


def test_consume_evicts_expired_tokens(monkeypatch) -> None:
    token = idempotency.new_token()
    idempotency.consume(token)

    real_monotonic = idempotency.time.monotonic
    monkeypatch.setattr(idempotency.time, "monotonic", lambda: real_monotonic() + idempotency._TOKEN_TTL_SECONDS + 1)

    assert idempotency.consume(token) is True
