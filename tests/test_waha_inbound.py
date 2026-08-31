from __future__ import annotations

from app.waha.inbound import InboundMessage, parse_inbound_message


def _event(**payload_overrides: object) -> dict:
    payload = {
        "id": "msg1",
        "from": "573001112233@c.us",
        "fromMe": False,
        "hasMedia": False,
        "body": "hola",
    }
    payload.update(payload_overrides)
    return {"event": "message", "session": "default", "payload": payload}


def test_parse_inbound_message_returns_message_for_valid_text_event() -> None:
    result = parse_inbound_message(_event())

    assert result == InboundMessage(
        chat_id="573001112233@c.us",
        text="hola",
        message_id="msg1",
        session="default",
    )


def test_parse_inbound_message_ignores_non_message_events() -> None:
    event = _event()
    event["event"] = "session.status"

    assert parse_inbound_message(event) is None


def test_parse_inbound_message_ignores_own_messages() -> None:
    assert parse_inbound_message(_event(fromMe=True)) is None


def test_parse_inbound_message_marks_media_messages_unsupported() -> None:
    result = parse_inbound_message(_event(hasMedia=True))

    assert result is not None
    assert result.is_unsupported is True
    assert result.text == ""


def test_parse_inbound_message_marks_non_audio_media_unsupported() -> None:
    result = parse_inbound_message(
        _event(hasMedia=True, media={"url": "http://x/f.jpg", "mimetype": "image/jpeg"})
    )

    assert result == InboundMessage(
        chat_id="573001112233@c.us",
        text="",
        message_id="msg1",
        session="default",
        is_unsupported=True,
    )


def test_parse_inbound_message_lets_through_audio_message() -> None:
    result = parse_inbound_message(
        _event(
            hasMedia=True,
            body="",
            media={"url": "http://localhost:3000/api/files/msg1.oga", "mimetype": "audio/ogg; codecs=opus"},
        )
    )

    assert result == InboundMessage(
        chat_id="573001112233@c.us",
        text="",
        message_id="msg1",
        session="default",
        is_audio=True,
        audio_media_path="/api/files/msg1.oga",
    )


def test_parse_inbound_message_audio_without_url_has_no_media_path() -> None:
    result = parse_inbound_message(
        _event(hasMedia=True, body="", media={"mimetype": "audio/ogg; codecs=opus", "error": "download failed"})
    )

    assert result is not None
    assert result.is_audio is True
    assert result.audio_media_path is None


def test_parse_inbound_message_ignores_status_broadcasts() -> None:
    assert parse_inbound_message(_event(**{"from": "status@broadcast"})) is None


def test_parse_inbound_message_ignores_empty_text() -> None:
    assert parse_inbound_message(_event(body="   ")) is None


def test_parse_inbound_message_ignores_missing_fields() -> None:
    event = _event()
    del event["payload"]["from"]

    assert parse_inbound_message(event) is None


def test_parse_inbound_message_strips_text() -> None:
    result = parse_inbound_message(_event(body="  hola  "))

    assert result is not None
    assert result.text == "hola"


def test_parse_inbound_message_extracts_sender_name_from_top_level_notify_name() -> None:
    result = parse_inbound_message(_event(notifyName="Juan Pérez"))

    assert result is not None
    assert result.sender_name == "Juan Pérez"


def test_parse_inbound_message_extracts_sender_name_from_data_notify_name() -> None:
    result = parse_inbound_message(_event(_data={"notifyName": "Juan Pérez"}))

    assert result is not None
    assert result.sender_name == "Juan Pérez"


def test_parse_inbound_message_extracts_sender_name_from_data_push_name() -> None:
    result = parse_inbound_message(_event(_data={"pushName": "Juan Pérez"}))

    assert result is not None
    assert result.sender_name == "Juan Pérez"


def test_parse_inbound_message_extracts_sender_name_from_gows_info_push_name() -> None:
    result = parse_inbound_message(_event(_data={"Info": {"PushName": "Juan Pérez"}}))

    assert result is not None
    assert result.sender_name == "Juan Pérez"


def test_parse_inbound_message_sender_name_is_none_when_not_present() -> None:
    result = parse_inbound_message(_event())

    assert result is not None
    assert result.sender_name is None
