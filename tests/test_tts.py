from types import SimpleNamespace

from heiddoon import server
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


def test_build_tts_payload_includes_human_like_instruction() -> None:
    payload = _build_tts_payload("Get back to work", voice="en-us", style="calm", emotion="neutral")

    assert "instructions" in payload
    assert "human-like" in payload["instructions"].lower()


def test_prefers_piper_backend_when_available(monkeypatch) -> None:
    monkeypatch.setattr(server, "settings", SimpleNamespace(tts_backend="auto", tts_enabled=True, tts_piper_model="mock-model"))
    monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/piper")

    assert server._should_use_piper_backend() is True
