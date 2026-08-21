from __future__ import annotations

from app.forms.link_token import sign_deal_id, verify_deal_id_token


def test_verify_accepts_matching_token():
    token = sign_deal_id("42", "secret")

    assert verify_deal_id_token("42", token, "secret") is True


def test_verify_rejects_token_for_a_different_deal():
    token = sign_deal_id("42", "secret")

    assert verify_deal_id_token("99", token, "secret") is False


def test_verify_rejects_token_signed_with_a_different_secret():
    token = sign_deal_id("42", "secret")

    assert verify_deal_id_token("42", token, "otro-secret") is False


def test_verify_rejects_missing_token():
    assert verify_deal_id_token("42", None, "secret") is False
    assert verify_deal_id_token("42", "", "secret") is False
