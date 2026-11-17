"""Tests for the output guardrail cascade. No network, no LLM.

Run:  python -m pytest tests/test_output_guardrail.py -v
"""
import app.safety.guardrails as guardrails

DIAGNOSIS = "Based on your symptoms, you have a migraine."
CONDITIONAL = "See a doctor if you have underlying health conditions."
PLAIN = "Rest and drink plenty of fluids."


def _judge_down(answer):
    raise ConnectionError("simulated outage")


def test_unflagged_answer_passes_without_calling_the_judge(monkeypatch):
    calls = []
    monkeypatch.setattr(guardrails, "llm_output_check", lambda a: calls.append(a) or True)
    assert guardrails.check_output(PLAIN) is None
    assert calls == []  # no pattern match -> no extra LLM call


def test_flagged_answer_is_blocked_when_judge_says_unsafe(monkeypatch):
    monkeypatch.setattr(guardrails, "llm_output_check", lambda a: True)
    assert guardrails.check_output(DIAGNOSIS) == guardrails.BLOCKED_MESSAGE


def test_flagged_answer_passes_when_judge_says_safe(monkeypatch):
    monkeypatch.setattr(guardrails, "llm_output_check", lambda a: False)
    assert guardrails.check_output(CONDITIONAL) is None


def test_flagged_answer_is_blocked_when_judge_is_down(monkeypatch):
    # The floor: a flagged answer never gets through just because the API failed.
    monkeypatch.setattr(guardrails, "llm_output_check", _judge_down)
    assert guardrails.check_output(DIAGNOSIS) == guardrails.BLOCKED_MESSAGE
    assert guardrails.check_output(CONDITIONAL) == guardrails.BLOCKED_MESSAGE


def test_judge_reply_parsing():
    # "SAFE" must not be mistaken for "UNSAFE" or the other way round.
    import app.safety.guardrails as g
    original = g.ask
    try:
        g.ask = lambda prompt, max_tokens=10: "SAFE"
        assert g.llm_output_check(CONDITIONAL) is False
        g.ask = lambda prompt, max_tokens=10: "UNSAFE"
        assert g.llm_output_check(DIAGNOSIS) is True
    finally:
        g.ask = original

