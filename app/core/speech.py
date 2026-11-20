"""Speech-to-text for WhatsApp voice notes (OpenAI gpt-transcribe).

Claude cannot take audio input, so a voice note is turned into text here
FIRST. The text then goes through exactly the same path as a typed message:
input safety gate on the original words, crew, output guardrail, translation.
Nothing about safety is special-cased for voice.

Privacy note: the audio is sent to OpenAI for transcription. The transcript
is not logged here.
"""
from openai import OpenAI

from config.settings import settings

# Formats OpenAI's transcription endpoint accepts, by MIME type.
# WhatsApp voice notes arrive as "audio/ogg; codecs=opus".
_EXTENSIONS = {
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/flac": "flac",
}

# Expected spoken languages. A hint, not a filter: helps with Hindi and
# Hinglish voice notes. Only gpt-transcribe accepts the "languages" field.
EXPECTED_LANGUAGES = ["hi", "en"]


class UnsupportedAudio(Exception):
    """The audio format can't be transcribed (e.g. some phones send AMR/AAC)."""


class EmptyTranscript(Exception):
    """Transcription ran but heard nothing usable (silence, noise)."""


_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _client = OpenAI(api_key=settings.openai_api_key, timeout=60)
    return _client


def transcribe(data: bytes, mime_type: str) -> str:
    """Return the text spoken in a voice note.

    Raises UnsupportedAudio, EmptyTranscript, or the OpenAI client's own
    errors. The caller decides what to tell the user; every failure path
    there still ends in a reply that mentions 112 - never silence.
    """
    base_type = (mime_type or "").split(";")[0].strip().lower()
    ext = _EXTENSIONS.get(base_type)
    if not ext:
        raise UnsupportedAudio(base_type or "unknown")

    kwargs = {}
    if settings.stt_model.startswith("gpt-transcribe"):
        kwargs["extra_body"] = {"languages": EXPECTED_LANGUAGES}

    result = _get_client().audio.transcriptions.create(
        model=settings.stt_model,
        file=(f"voice.{ext}", data, base_type),
        **kwargs,
    )
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        raise EmptyTranscript()
    return text