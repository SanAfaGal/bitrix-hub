from __future__ import annotations

from app.waha.phone import from_chat_id, lid_from_chat_id, to_chat_id


def test_to_chat_id_plain_local_number() -> None:
    assert to_chat_id("3001112233") == "573001112233@c.us"


def test_to_chat_id_with_spaces_and_dashes() -> None:
    assert to_chat_id("300 111-2233") == "573001112233@c.us"


def test_to_chat_id_with_parentheses() -> None:
    assert to_chat_id("(300) 111 2233") == "573001112233@c.us"


def test_to_chat_id_with_explicit_plus_country_code() -> None:
    assert to_chat_id("+57 300 111 2233") == "573001112233@c.us"


def test_to_chat_id_with_00_country_prefix() -> None:
    assert to_chat_id("0057 300 1112233") == "573001112233@c.us"


def test_to_chat_id_does_not_double_prepend_when_country_code_already_present() -> None:
    # 12 digits, ya trae el 57 — no se le debe volver a anteponer.
    assert to_chat_id("+573001112233") == "573001112233@c.us"


def test_to_chat_id_other_country_code_kept_as_is() -> None:
    assert to_chat_id("+1 305 555 1234") == "13055551234@c.us"


def test_to_chat_id_returns_none_on_empty() -> None:
    assert to_chat_id("") is None
    assert to_chat_id("   ") is None


def test_to_chat_id_returns_none_on_ambiguous_short_number_without_country_code() -> None:
    assert to_chat_id("1112233") is None


def test_to_chat_id_returns_none_on_too_long() -> None:
    assert to_chat_id("+" + "1" * 20) is None


def test_to_chat_id_custom_default_country_code() -> None:
    assert to_chat_id("3001112233", default_country_code="52") == "523001112233@c.us"


def test_from_chat_id_returns_digits() -> None:
    assert from_chat_id("573001112233@c.us") == "573001112233"


def test_from_chat_id_roundtrips_with_to_chat_id() -> None:
    chat_id = to_chat_id("300 111 2233")
    assert chat_id is not None
    assert from_chat_id(chat_id) == "573001112233"


def test_from_chat_id_returns_none_for_group_chat() -> None:
    assert from_chat_id("123456-789@g.us") is None


def test_from_chat_id_returns_none_on_empty() -> None:
    assert from_chat_id("") is None


def test_from_chat_id_returns_none_on_malformed_input() -> None:
    assert from_chat_id("no-at-sign") is None
    assert from_chat_id("abc123@c.us") is None


def test_lid_from_chat_id_returns_identifier() -> None:
    assert lid_from_chat_id("123456789012345@lid") == "123456789012345"


def test_lid_from_chat_id_returns_none_for_normal_chat() -> None:
    assert lid_from_chat_id("573001112233@c.us") is None


def test_lid_from_chat_id_returns_none_for_group_chat() -> None:
    assert lid_from_chat_id("123456-789@g.us") is None


def test_lid_from_chat_id_returns_none_on_empty() -> None:
    assert lid_from_chat_id("") is None


def test_lid_from_chat_id_returns_none_on_malformed_input() -> None:
    assert lid_from_chat_id("no-at-sign") is None
    assert lid_from_chat_id("@lid") is None
