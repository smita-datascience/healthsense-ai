"""Tests for the lab report reader and its WhatsApp wiring. No network, no LLM.

Run:  python -m pytest tests/test_report.py -v
"""
import json

import pytest

import app.agents.report as report
import app.safety.guardrails as guardrails
from app.whatsapp import routes

PNG = b"\x89PNG fake image bytes"
EXTRACTED = {
    "is_lab_report": True,
    "tests": [
        {"name": "Haemoglobin", "value": "10.2", "unit": "g/dL", "reference_range": "12.0 - 15.5", "flag": "L"},
        {"name": "TSH", "value": "2.1", "unit": "uIU/mL", "reference_range": "0.4 - 4.0", "flag": ""},
    ],
}
SAFE_EXPLANATION = "Haemoglobin carries oxygen. It is below the report's range. Please discuss it with your doctor."


# -- 2. COMPARE: pure Python, so it can be tested exactly ----------------------

@pytest.mark.parametrize("value, ref, flag, expected", [
    ("10.2", "12.0 - 15.5", "", "below"),
    ("13.5", "12.0-15.5", "", "within"),
    ("16", "12 – 15.5", "", "above"),
    ("5.9", "4.0 to 5.6", "", "above"),
    ("250", "<200", "", "above"),
    ("180", "< 200", "", "within"),
    ("35", ">40", "", "below"),
    ("0.8", "up to 1.2", "", "within"),
    ("1,20,000", "1,50,000 - 4,50,000", "", "below"),   # Indian digit grouping
    ("7.2", "", "H", "above"),                          # no range: use the report's flag
    ("3.1", "", "L", "below"),
    ("Negative", "Negative", "", "unknown"),
    ("6.0", "", "", "unknown"),
])
def test_range_status(value, ref, flag, expected):
    assert report.range_status(value, ref, flag) == expected


def test_parse_extraction_tolerates_chatter_and_rejects_garbage():
    assert report.parse_extraction('Here you go: {"is_lab_report": true, "tests": []} ok')["is_lab_report"]
    assert report.parse_extraction("I could not read it") is None
    assert report.parse_extraction('{"tests": "not a list"}') is None


def test_build_table_adds_status_and_skips_nameless_rows():
    rows = report.build_table(EXTRACTED["tests"] + [{"name": "", "value": "1"}])
    assert [r["status"] for r in rows] == ["below", "within"]


def test_extraction_prompt_excludes_personal_identifiers():
    assert "Do NOT copy the patient's name" in report.EXTRACT_PROMPT


# -- Full pipeline with fakes --------------------------------------------------

@pytest.fixture
def fakes(monkeypatch):
    calls = {"vision": 0, "saved": []}

    def fake_vision(prompt, data, mime_type, max_tokens=1500):
        calls["vision"] += 1
        return calls.get("vision_reply", json.dumps(EXTRACTED))

    monkeypatch.setattr(report, "ask_with_file", fake_vision)
    monkeypatch.setattr(report, "ask", lambda prompt, max_tokens=1500: calls.get("explanation", SAFE_EXPLANATION))
    monkeypatch.setattr(report, "from_english", lambda text, lang: f"[{lang}] {text}")
    monkeypatch.setattr(report, "recent_history", lambda user_id, limit=1: "")
    monkeypatch.setattr(report, "save_interaction", lambda u, q, a: calls["saved"].append((q, a)))
    monkeypatch.setattr(guardrails, "llm_emergency_check", lambda q: False)
    monkeypatch.setattr(guardrails, "llm_output_check", lambda a: False)
    return calls


def test_english_report_is_explained(fakes):
    assert report.explain_report(PNG, "image/png") == SAFE_EXPLANATION
    assert fakes["saved"] and fakes["saved"][0][0] == "[lab report]"


def test_hinglish_caption_gets_translated_reply(fakes):
    reply = report.explain_report(PNG, "image/png", caption="yeh meri report hai, samjhao kya hai")
    assert reply == f"[hinglish] {SAFE_EXPLANATION}"


def test_hindi_caption_gets_hindi_fixed_message(fakes):
    fakes["vision_reply"] = '{"is_lab_report": false, "tests": []}'
    reply = report.explain_report(PNG, "image/png", caption="यह मेरी रिपोर्ट है")
    assert reply == report.REPLIES["not_a_report"]["hi"]


def test_unreadable_extraction(fakes):
    fakes["vision_reply"] = "sorry, too blurry"
    assert report.explain_report(PNG, "image/png") == report.REPLIES["unreadable"]["en"]


def test_report_with_no_values_is_unreadable(fakes):
    fakes["vision_reply"] = '{"is_lab_report": true, "tests": []}'
    assert report.explain_report(PNG, "image/png") == report.REPLIES["unreadable"]["en"]


def test_unsupported_type_and_size_never_reach_the_model(fakes):
    assert report.explain_report(b"x", "audio/ogg") == report.REPLIES["unsupported"]["en"]
    big = b"x" * (report.MAX_BYTES + 1)
    assert report.explain_report(big, "image/png") == report.REPLIES["unsupported"]["en"]
    assert fakes["vision"] == 0


def test_emergency_caption_is_escalated_before_reading(fakes, monkeypatch):
    monkeypatch.setattr(guardrails, "llm_emergency_check", lambda q: True)
    reply = report.explain_report(PNG, "image/png", caption="seene mein dard hai, yeh report dekho")
    assert reply == guardrails.EMERGENCY_MESSAGES["hinglish"]
    assert fakes["vision"] == 0


def test_unsafe_explanation_is_blocked_before_translation(fakes, monkeypatch):
    fakes["explanation"] = "Your results indicate anaemia. Take 100 mg iron daily."
    monkeypatch.setattr(guardrails, "llm_output_check", lambda a: True)
    reply = report.explain_report(PNG, "image/png", caption="meri report samjhao kya hai")
    assert reply == guardrails.BLOCKED_MESSAGES["hinglish"]


def test_trace_shows_intermediate_steps(fakes):
    trace = {}
    report.explain_report(PNG, "image/png", trace=trace)
    assert [r["status"] for r in trace["rows"]] == ["below", "within"]
    assert trace["english"] == SAFE_EXPLANATION
    assert trace["guardrail_blocked"] is False


# -- WhatsApp wiring -----------------------------------------------------------

def media_payload(kind="image", caption="meri report", mime="image/jpeg"):
    media = {"id": "MEDIA123", "mime_type": mime, "caption": caption}
    return {"entry": [{"changes": [{"value": {"messages": [
        {"id": "wamid.r1", "from": "919800000000", "type": kind, kind: media}
    ]}}]}]}


@pytest.mark.parametrize("kind, mime", [("image", "image/jpeg"), ("document", "application/pdf")])
def test_extract_messages_reads_media_fields(kind, mime):
    msg = routes.extract_messages(media_payload(kind, mime=mime))[0]
    assert (msg["type"], msg["media_id"], msg["mime_type"], msg["caption"]) == (kind, "MEDIA123", mime, "meri report")


def test_image_message_is_downloaded_and_explained(monkeypatch):
    sent, seen = [], {}
    monkeypatch.setattr(routes, "send_text", lambda to, body: sent.append((to, body)))
    monkeypatch.setattr(routes, "download_media", lambda media_id: (PNG, "image/jpeg"))

    def fake_explain(data, mime_type, caption="", user_id=""):
        seen.update(data=data, mime=mime_type, caption=caption, user=user_id)
        return "REPORT EXPLAINED"

    monkeypatch.setattr(report, "explain_report", fake_explain)
    routes.process_message(routes.extract_messages(media_payload())[0])
    assert sent == [("919800000000", "REPORT EXPLAINED")]
    assert seen["data"] == PNG and seen["caption"] == "meri report"
    assert "919800000000" not in seen["user"]          # memory sees only the hash


def test_too_large_media_gets_polite_reply(monkeypatch):
    sent = []
    monkeypatch.setattr(routes, "send_text", lambda to, body: sent.append(body))

    def too_big(media_id):
        raise routes.MediaTooLarge(50_000_000)

    monkeypatch.setattr(routes, "download_media", too_big)
    routes.process_message(routes.extract_messages(media_payload())[0])
    assert sent == [routes.TOO_LARGE_REPLY]
