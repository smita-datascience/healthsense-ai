"""Tests for multi-language support. No network, no LLM.

Run:  python -m pytest tests/test_language.py -v
"""
import pytest

import app.safety.guardrails as guardrails
from app.core.language import detect_language
from app.evaluation.independent_tests import INDEPENDENT_TESTS
from app.evaluation.run_multilingual_eval import MULTILINGUAL_TESTS
from app.evaluation.safety_tests import EMERGENCY_TESTS


# -- Language detection --------------------------------------------------------

def test_every_english_test_message_is_detected_as_english():
    english = [t["message"] for t in EMERGENCY_TESTS + INDEPENDENT_TESTS]
    wrong = [m for m in english if detect_language(m) != "en"]
    assert wrong == []


def test_every_multilingual_test_message_is_detected_correctly():
    for t in MULTILINGUAL_TESTS:
        expected = "hi" if t["category"].startswith("hi_") else "hinglish"
        assert detect_language(t["message"]) == expected, t["message"]


@pytest.mark.parametrize("text, lang", [
    ("what is a healthy diet", "en"),
    ("I have had a cough for two days", "en"),
    ("मुझे बुखार है", "hi"),
    ("mujhe kal se bukhar hai", "hinglish"),
])
def test_detect_language_examples(text, lang):
    assert detect_language(text) == lang


# -- Safety messages come out in the user's language --------------------------

def _layer2_down(question):
    raise ConnectionError("simulated outage")


@pytest.mark.parametrize("message, lang", [
    ("मेरे सीने में दर्द है और साँस नहीं आ रही", "hi"),
    ("seene mein dard hai aur saans nahi aa rahi", "hinglish"),
    ("I have chest pain", "en"),
])
def test_emergency_message_language_even_when_llm_is_down(monkeypatch, message, lang):
    monkeypatch.setattr(guardrails, "llm_emergency_check", _layer2_down)
    assert guardrails.check_input(message) == guardrails.EMERGENCY_MESSAGES[lang]


def test_emergency_message_language_when_llm_flags_it(monkeypatch):
    monkeypatch.setattr(guardrails, "llm_emergency_check", lambda q: True)
    assert guardrails.check_input("माँ बेहोश हो गई हैं") == guardrails.EMERGENCY_MESSAGES["hi"]


def test_blocked_message_is_in_requested_language():
    unsafe = "You have diabetes. Take 500 mg twice a day."
    assert guardrails.check_output(unsafe, "hi") == guardrails.BLOCKED_MESSAGES["hi"]
    assert guardrails.check_output(unsafe, "hinglish") == guardrails.BLOCKED_MESSAGES["hinglish"]
    assert guardrails.check_output(unsafe) == guardrails.BLOCKED_MESSAGE


def test_number_unit_dosing_is_caught_in_hindi_text():
    # The second, post-translation pass relies on this.
    assert guardrails.check_output("दिन में दो बार 500 mg लें", "hi") is not None


def test_every_language_has_both_messages():
    for lang in ("en", "hi", "hinglish"):
        assert guardrails.EMERGENCY_MESSAGES[lang]
        assert guardrails.BLOCKED_MESSAGES[lang]
        assert "112" in guardrails.EMERGENCY_MESSAGES[lang]
        assert "108" in guardrails.EMERGENCY_MESSAGES[lang]