"""Tests for WhatsApp voice notes - no real audio, network or API credits.

The download, OpenAI and the crew are replaced by small fakes, so these tests
check the WIRING: a voice note is recognised, the transcript goes unchanged
into the same answer() a typed message uses (so the input safety gate sees
exactly what was said), and every failure path still replies with 112.
"""
import sys
import types

import pytest

from app.core import speech
from app.whatsapp import routes


def _audio_msg(mime="audio/ogg; codecs=opus"):
    return {
        "id": "wamid.TEST",
        "from": "919800000000",
        "type": "audio",
        "text": "",
        "media_id": "MEDIA123",
        "mime_type": mime,
        "caption": "",
    }


@pytest.fixture
def wiring(monkeypatch):
    """Fake download, fake crew, captured send_text."""
    sent = {}
    calls = {}

    monkeypatch.setattr(routes, "pseudonymous_user_id", lambda phone: f"user-{phone}")
    monkeypatch.setattr(routes, "download_media",
                        lambda media_id: (b"fake-ogg-bytes", "audio/ogg; codecs=opus"))
    monkeypatch.setattr(routes, "send_text",
                        lambda phone, text: sent.update(phone=phone, text=text))

    def fake_answer(question, user_id="demo_user"):
        calls["question"] = question
        calls["user_id"] = user_id
        return f"ANSWER to: {question}"

    fake_crew = types.ModuleType("app.agents.crew")
    fake_crew.answer = fake_answer
    monkeypatch.setitem(sys.modules, "app.agents.crew", fake_crew)
    return sent, calls


# ---------------------------------------------------------------- parsing
def test_extract_messages_picks_up_voice_note():
    payload = {"entry": [{"changes": [{"value": {"messages": [{
        "id": "wamid.1", "from": "919800000000", "type": "audio",
        "audio": {"id": "MEDIA123", "mime_type": "audio/ogg; codecs=opus", "voice": True},
    }]}}]}]}
    [msg] = routes.extract_messages(payload)
    assert msg["type"] == "audio"
    assert msg["media_id"] == "MEDIA123"
    assert msg["mime_type"].startswith("audio/ogg")


# ---------------------------------------------------------------- happy path
def test_transcript_goes_unchanged_into_answer(wiring, monkeypatch):
    sent, calls = wiring
    heard = "I have crushing chest pain spreading to my left arm"
    monkeypatch.setattr(speech, "transcribe", lambda data, mime: heard)

    routes.process_message(_audio_msg())

    # The safety gate inside answer() sees exactly what was said.
    assert calls["question"] == heard
    assert calls["user_id"] == "user-919800000000"
    # The user sees what we heard, then the answer.
    assert sent["text"].startswith(f'🎤 "{heard}"')
    assert f"ANSWER to: {heard}" in sent["text"]


def test_hindi_transcript_passes_through(wiring, monkeypatch):
    sent, calls = wiring
    heard = "बुखार में क्या खाना चाहिए?"
    monkeypatch.setattr(speech, "transcribe", lambda data, mime: heard)

    routes.process_message(_audio_msg())

    assert calls["question"] == heard
    assert heard in sent["text"]


# ---------------------------------------------------------------- never silence
def _raise(exc):
    def _f(*args, **kwargs):
        raise exc
    return _f


@pytest.mark.parametrize(
    "error, expected_reply",
    [
        (speech.UnsupportedAudio("audio/amr"), routes.AUDIO_FORMAT_REPLY),
        (speech.EmptyTranscript(), routes.EMPTY_AUDIO_REPLY),
        (RuntimeError("OpenAI unavailable / no credits"), routes.FALLBACK_REPLY),
    ],
)
def test_every_failure_still_replies_with_112(wiring, monkeypatch, error, expected_reply):
    sent, calls = wiring
    monkeypatch.setattr(speech, "transcribe", _raise(error))

    routes.process_message(_audio_msg())

    assert sent["text"] == expected_reply
    assert "112" in sent["text"]
    assert "question" not in calls  # the crew never ran on a failed transcript


# ---------------------------------------------------------------- speech module
class _FakeClient:
    def __init__(self, text):
        self.kwargs = None
        self._text = text
        self.audio = types.SimpleNamespace(
            transcriptions=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return types.SimpleNamespace(text=self._text)


def test_transcribe_sends_ogg_with_language_hint(monkeypatch):
    client = _FakeClient("  What helps with a mild headache?  ")
    monkeypatch.setattr(speech, "_get_client", lambda: client)
    monkeypatch.setattr(speech.settings, "stt_model", "gpt-transcribe")

    text = speech.transcribe(b"bytes", "audio/ogg; codecs=opus")

    assert text == "What helps with a mild headache?"
    assert client.kwargs["model"] == "gpt-transcribe"
    filename, data, mime = client.kwargs["file"]
    assert filename == "voice.ogg" and data == b"bytes" and mime == "audio/ogg"
    assert client.kwargs["extra_body"] == {"languages": ["hi", "en"]}


def test_unsupported_format_never_calls_the_api(monkeypatch):
    def must_not_be_called():
        raise AssertionError("API should not be called for an unsupported format")

    monkeypatch.setattr(speech, "_get_client", must_not_be_called)
    with pytest.raises(speech.UnsupportedAudio):
        speech.transcribe(b"bytes", "audio/amr")


def test_silence_raises_empty_transcript(monkeypatch):
    monkeypatch.setattr(speech, "_get_client", lambda: _FakeClient("   "))
    with pytest.raises(speech.EmptyTranscript):
        speech.transcribe(b"bytes", "audio/ogg")