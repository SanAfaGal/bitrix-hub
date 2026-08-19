from __future__ import annotations

from app.waha.phone import extract_phone_from_contact, to_chat_id


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


def test_extract_phone_from_contact_prefers_mobile() -> None:
    contact = {
        "PHONE": [
            {"VALUE": "6015551234", "VALUE_TYPE": "WORK"},
            {"VALUE": "3001112233", "VALUE_TYPE": "MOBILE"},
        ]
    }
    assert extract_phone_from_contact(contact) == "3001112233"


def test_extract_phone_from_contact_falls_back_to_first_available() -> None:
    contact = {"PHONE": [{"VALUE": "6015551234", "VALUE_TYPE": "WORK"}]}
    assert extract_phone_from_contact(contact) == "6015551234"


def test_extract_phone_from_contact_returns_none_when_no_phone() -> None:
    assert extract_phone_from_contact({}) is None
    assert extract_phone_from_contact({"PHONE": []}) is None
    assert extract_phone_from_contact({"PHONE": [{"VALUE": "", "VALUE_TYPE": "WORK"}]}) is None
