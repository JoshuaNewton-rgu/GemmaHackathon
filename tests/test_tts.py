from heiddoon.server import _build_tts_payload


def test_build_tts_payload_includes_voice_and_text() -> None:
    payload = _build_tts_payload("Get back to work", voice="en-us")

    assert payload["inputs"] == "Get back to work"
    assert payload["voice"] == "en-us"


def test_build_tts_payload_includes_expressive_fields() -> None:
    payload = _build_tts_payload("Get back to work", voice="en-us", style="happy", emotion="energetic", speed=1.2)

    assert payload["style"] == "happy"
    assert payload["emotion"] == "energetic"
    assert payload["speed"] == 1.2
