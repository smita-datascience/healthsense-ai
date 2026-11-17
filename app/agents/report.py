"""Lab report reader for HealthSense AI (v2, MAI parity item 2).

A user sends a photo or PDF of a lab report; we explain each value in plain
language. Pipeline - each step does ONE job, and the job that must be exact is
never given to the model:

  1. READ      Claude vision reads the report and copies each test into JSON:
               name, value, unit, the report's own reference range, any H/L
               flag. Copy only - no interpretation. Personal identifiers
               (name, ID, phone, address) are deliberately NOT extracted.
  2. COMPARE   Plain Python decides below / within / above range. Comparing
               two numbers is arithmetic, not judgement; a model can get it
               wrong, a comparison operator cannot.
  3. EXPLAIN   Claude writes a plain-language explanation in English from the
               table - using the status from step 2, never recomputing it.
  4. GUARD     The output guardrail (patterns flag, LLM judges) checks the
               English text.
  5. TRANSLATE Only text that passed the guardrail is translated for the user.

The image itself is never written to disk; only the reply is stored, like any
other answer.
"""
import json
import re

from app.core.language import detect_language, from_english
from app.core.llm import ask, ask_with_file
from app.memory.memory import recent_history, save_interaction
from app.safety.guardrails import check_input, check_output

SUPPORTED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# Fixed replies, pre-translated like the safety messages.
REPLIES = {
    "unsupported": {
        "en": "I can read lab reports sent as a photo (JPG or PNG) or a PDF under 10 MB. Please send it in one of those formats.",
        "hi": "मैं लैब रिपोर्ट फ़ोटो (JPG या PNG) या 10 MB से छोटी PDF के रूप में पढ़ सकता हूँ। कृपया इनमें से किसी एक फ़ॉर्मेट में भेजें।",
        "hinglish": "Main lab report photo (JPG ya PNG) ya 10 MB se chhoti PDF ke roop mein padh sakta hoon. Kripya inmein se kisi ek format mein bhejein.",
    },
    "not_a_report": {
        "en": "This doesn't look like a lab report to me. If it is one, please send a clear photo of the page with the test results.",
        "hi": "यह मुझे लैब रिपोर्ट नहीं लग रही। अगर यह रिपोर्ट है, तो कृपया टेस्ट रिज़ल्ट वाले पेज की साफ़ फ़ोटो भेजें।",
        "hinglish": "Yeh mujhe lab report nahi lag rahi. Agar yeh report hai, to kripya test results wale page ki saaf photo bhejein.",
    },
    "unreadable": {
        "en": "I couldn't read the values clearly. Please send a sharper photo - flat, in good light, with the whole results table visible.",
        "hi": "मैं वैल्यू साफ़ नहीं पढ़ पाया। कृपया एक साफ़ फ़ोटो भेजें - सीधी, अच्छी रोशनी में, और पूरी रिज़ल्ट टेबल दिखती हुई।",
        "hinglish": "Main values saaf nahi padh paaya. Kripya ek saaf photo bhejein - seedhi, achhi roshni mein, aur poori result table dikhti hui.",
    },
}

EXTRACT_PROMPT = (
    "You are reading a medical lab report so its values can be explained to "
    "the patient. Copy what is printed - do not interpret anything.\n\n"
    "Return ONLY a JSON object, no other text:\n"
    "{\n"
    '  "is_lab_report": true or false,\n'
    '  "tests": [\n'
    '    {"name": "...", "value": "...", "unit": "...",\n'
    '     "reference_range": "...", "flag": "..."}\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Copy names, values, units and reference ranges exactly as printed.\n"
    "- flag: copy any marker the report prints next to the value (H, L, High, "
    "Low, *), otherwise \"\".\n"
    "- Use \"\" for anything not printed. Never guess a reference range.\n"
    "- Do NOT copy the patient's name, age, ID, phone, address, or the "
    "doctor's or lab's details.\n"
    "- If the image is not a lab report, return "
    '{"is_lab_report": false, "tests": []}.\n'
    "- If it is a lab report but you cannot read the values, return "
    '{"is_lab_report": true, "tests": []}.'
)

_NUMBER = r"[-+]?\d+(?:\.\d+)?"


def _to_number(text: str):
    """'1,20,000' -> 120000.0 ; '13.5' -> 13.5 ; 'Negative' -> None."""
    match = re.search(_NUMBER, (text or "").replace(",", ""))
    return float(match.group()) if match else None


def range_status(value: str, reference_range: str, flag: str = "") -> str:
    """Return "below", "within", "above" or "unknown". Pure Python, no model.

    Understands the common printed forms: "12 - 15.5", "12–15.5", "12 to 15.5",
    "< 200", "<= 5.6", "up to 40", "> 40", ">= 60". Falls back to the
    report's own H/L flag when the range can't be parsed.
    """
    v = _to_number(value)
    r = (reference_range or "").replace(",", "").lower().strip()

    if v is not None and r:
        pair = re.search(rf"({_NUMBER})\s*(?:-|–|—|to)\s*({_NUMBER})", r)
        upper = re.search(rf"(?:<=?|≤|up to|upto|less than)\s*({_NUMBER})", r)
        lower = re.search(rf"(?:>=?|≥|more than|greater than)\s*({_NUMBER})", r)
        if pair:
            low, high = float(pair.group(1)), float(pair.group(2))
            if v < low:
                return "below"
            if v > high:
                return "above"
            return "within"
        if upper:
            return "above" if v > float(upper.group(1)) else "within"
        if lower:
            return "below" if v < float(lower.group(1)) else "within"

    f = (flag or "").strip().lower()
    if f in {"h", "high", "hi", "↑"}:
        return "above"
    if f in {"l", "low", "lo", "↓"}:
        return "below"
    return "unknown"


def parse_extraction(text: str):
    """Pull the JSON object out of the model's reply. None if it isn't valid."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tests", []), list):
        return None
    return data


def build_table(tests: list[dict]) -> list[dict]:
    """Add the Python-computed status to each extracted test."""
    rows = []
    for t in tests:
        if not isinstance(t, dict) or not str(t.get("name", "")).strip():
            continue
        row = {k: str(t.get(k, "")).strip() for k in ("name", "value", "unit", "reference_range", "flag")}
        row["status"] = range_status(row["value"], row["reference_range"], row["flag"])
        rows.append(row)
    return rows


def explain_prompt(rows: list[dict]) -> str:
    lines = "\n".join(
        f"- {r['name']}: {r['value']} {r['unit']} | report's range: "
        f"{r['reference_range'] or 'not printed'} | status: {r['status']}"
        for r in rows
    )
    return (
        "You are explaining a lab report to a member of the public, in plain, "
        "calm English. Here are the values, already compared with the report's "
        "own reference ranges:\n\n"
        f"{lines}\n\n"
        "Write the explanation:\n"
        "- Start with the values marked below or above, then briefly list the "
        "ones within range.\n"
        "- For each value: one sentence on what the test measures, then say "
        "whether it is below, within or above the report's range. Use the "
        "status given - do not recalculate it. For 'unknown', say the report "
        "doesn't show a range you can compare against.\n"
        "- Do NOT diagnose, name a condition the person has, guess causes, or "
        "suggest any medicine or dose.\n"
        "- Suggest discussing any out-of-range values with the doctor who "
        "ordered the test.\n"
        "- End with one line saying this is general information, not a "
        "diagnosis or medical advice.\n"
        "Keep it short enough to read on a phone."
    )


def explain_report(data: bytes, mime_type: str, caption: str = "",
                   user_id: str = "demo_user", trace: dict | None = None) -> str:
    """Full pipeline: file in, safe plain-language reply out.

    Pass a dict as `trace` to see the intermediate steps (used by the demo
    runner): the extracted table and the English text before the guardrail.
    """
    trace = trace if trace is not None else {}
    caption = (caption or "").strip()
    if caption:
        lang = detect_language(caption)
    else:
        lang = detect_language(recent_history(user_id, limit=1) or "")

    # A caption is a message like any other: emergency check first.
    if caption:
        emergency = check_input(caption, lang)
        if emergency:
            save_interaction(user_id, f"[lab report] {caption}", emergency)
            return emergency

    if mime_type not in SUPPORTED_TYPES or len(data) > MAX_BYTES:
        return REPLIES["unsupported"][lang]

    extracted = parse_extraction(ask_with_file(EXTRACT_PROMPT, data, mime_type))
    if extracted is None:
        return REPLIES["unreadable"][lang]
    if not extracted.get("is_lab_report", False):
        return REPLIES["not_a_report"][lang]
    rows = build_table(extracted.get("tests", []))
    trace["rows"] = rows
    if not rows:
        return REPLIES["unreadable"][lang]

    english = ask(explain_prompt(rows), max_tokens=1500).strip()
    trace["english"] = english

    reply = check_output(english, lang)
    trace["guardrail_blocked"] = reply is not None
    if reply is None:
        reply = english
        if lang != "en":
            try:
                translated = from_english(english, lang)
                reply = check_output(translated, lang) or translated
            except Exception:
                pass  # translation failed: send the already-checked English text

    save_interaction(user_id, f"[lab report] {caption}".strip(), reply)
    return reply
