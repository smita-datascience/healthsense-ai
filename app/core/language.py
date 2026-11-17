"""Language handling for HealthSense AI - "English core, translation at the edges".

Design:
  1. detect_language()  deterministic, no API call. Works even when the LLM is
                        down, so the emergency message always comes out in the
                        user's language.
  2. to_english()       the user's question is translated to English BEFORE the
                        crew runs. Retrieval (keyword search over an English
                        knowledge base) and the output guardrail (English regex
                        patterns) both only understand English.
  3. from_english()     the crew's answer is translated back LAST, after the
                        output guardrail has checked the English version.

Why not just tell the crew "reply in Hindi"? Then the output guardrail would be
reading Hindi text with English patterns - "आपको डायबिटीज़ है" ("you have
diabetes") would sail straight past a check built to catch "you have". A
guardrail that cannot read the language is not a guardrail.

Supported: "en" (English), "hi" (Hindi, Devanagari script),
           "hinglish" (Hindi written in Roman letters, often mixed with English).
"""
import re

from app.core.llm import ask

# Common Hindi function words as people type them in Roman letters. Chosen
# because they are frequent in Hinglish and are not ordinary English words.
HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "mein", "kya", "kaise", "kyun", "kyon",
    "mera", "meri", "mere", "mujhe", "aap", "aapko", "hoon", "hun", "raha",
    "rahi", "rahe", "ka", "ki", "ke", "ko", "se", "bhi", "toh", "tha", "thi",
    "karna", "kar", "karein", "chahiye", "bahut", "abhi", "agar", "kuch",
    "sab", "yeh", "ye", "woh", "wo", "gaya", "gayi", "liya", "kaun", "kitna",
}

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[a-z]+")

LANGUAGE_NAMES = {
    "hi": "simple, everyday Hindi written in Devanagari script",
    "hinglish": (
        "Hinglish - conversational Hindi written in Roman (English) letters, "
        "the way people type on WhatsApp in India"
    ),
}


def detect_language(text: str) -> str:
    """Return "hi", "hinglish" or "en". No API call - pure rules."""
    devanagari = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    if devanagari and devanagari >= 0.3 * (devanagari + latin):
        return "hi"

    words = _WORD.findall(text.lower())
    markers = sum(1 for w in words if w in HINGLISH_MARKERS)
    if markers >= 2 and markers >= 0.15 * len(words):
        return "hinglish"
    return "en"


def to_english(text: str) -> str:
    """Translate a user's question into English for the crew."""
    prompt = (
        "Translate this health message into clear English. Keep the meaning "
        "exactly - every symptom, time, person and detail. Do NOT answer it, "
        "add advice, or soften anything. Output only the translation.\n\n"
        f"Message: {text}"
    )
    return ask(prompt, max_tokens=500).strip()


def from_english(text: str, lang: str) -> str:
    """Translate the crew's (already safety-checked) answer for the user."""
    prompt = (
        f"Translate this health information into {LANGUAGE_NAMES[lang]}. "
        "Keep medical words people in India usually say in English (BP, sugar, "
        "ECG, doctor) as they are. Do NOT add, remove, or soften anything - "
        "keep every caution and the closing disclaimer. Output only the "
        "translation.\n\n"
        f"Text:\n{text}"
    )
    return ask(prompt, max_tokens=1500).strip()