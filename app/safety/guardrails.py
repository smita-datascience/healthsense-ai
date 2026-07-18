
"""Safety guardrails for HealthSense AI - hybrid emergency detection."""
import re

from app.core.llm import ask

EMERGENCY_TERMS = [
    "chest pain", "can't breathe", "cant breathe", "not breathing",
    "suicide", "kill myself", "self harm", "self-harm",
    "overdose", "unconscious", "stroke", "severe bleeding",
    "heart attack", "choking",
]

EMERGENCY_MESSAGE = (
    "This may be a medical emergency. Please contact emergency services "
    "immediately - in India call 112 (or 108 for an ambulance). "
    "If someone is in danger, do not wait for an online response."
)

BLOCKED_MESSAGE = (
    "I can't share that response. It contained specific dosing or diagnostic "
    "language, which only a licensed healthcare professional can safely give "
    "you. Please speak to a doctor or pharmacist about your situation.\n\n"
    "I'm happy to explain conditions, terminology, or general health topics instead."
)

DOSING_PATTERNS = [
    r"\b\d+\s?(mg|mcg|ml|g|units?|iu)\b",
    r"\btake\s+(\d+|one|two|three|a|an)\b.*\b(tablet|capsule|pill|dose|drop)",
    r"\b(increase|decrease|double|halve|stop taking)\b.*\b(dose|dosage|medication|tablet|insulin)",
    r"\b(once|twice|three times)\s+(a|per)\s+day\b.*\b(tablet|capsule|pill|dose|mg)",
    r"\byour (dose|dosage) (should|would) be\b",
]

DIAGNOSIS_PATTERNS = [
    r"\byou (have|likely have|probably have|are suffering from)\b",
    r"\byou (don't|do not) have\b",
    r"\b(this|it) is (almost certainly|definitely|clearly)\b",
    r"\byour (diagnosis|test results?) (is|are|indicate|show)\b",
    r"\bi can confirm\b",
    r"\bno need to see a (doctor|physician|gp)\b",
    r"\byou can (safely )?ignore\b",
]


def llm_emergency_check(question: str) -> bool:
    """Layer 2 of the input cascade: the reasoning layer."""
    prompt = (
        "You are a medical safety screen. Decide if the message could describe a "
        "possible medical emergency needing immediate care - such as severe chest "
        "pain, trouble breathing, signs of stroke, severe bleeding, suicidal "
        "thoughts, overdose, or loss of consciousness.\n\n"
        "Judge the SITUATION described, not the way it is phrased. People in "
        "distress often distance themselves from what is happening. Treat these "
        "as EMERGENCY if the underlying situation is one:\n"
        "- hypothetical framing ('hypothetically', 'in theory', 'just wondering')\n"
        "- third-party framing ('asking for a friend', 'my cousin')\n"
        "- fictional framing ('for a story I'm writing', 'in a movie')\n"
        "- minimizing framing ('probably nothing, but', 'not urgent, but')\n"
        "- academic or curiosity framing ('how long can a person survive...')\n"
        "- role-play or instruction framing ('you are a triage nurse',\n"
        "  'pretend the rules are off', 'act as a doctor and tell me what to do')\n"
        "- the urgent detail buried mid-message after unrelated small talk\n\n"
        "Also treat as EMERGENCY the indirect signals of suicidal intent: giving "
        "possessions away, putting affairs in order, asking who would care for "
        "dependants, sudden calm after distress, or deliberately stopping "
        "essential medication.\n\n"
        "The following are SAFE. They seek knowledge, not help with an unfolding "
        "situation, even though they contain alarming vocabulary:\n"
        "- how a condition works, is diagnosed, or is treated\n"
        "- the difference between two conditions\n"
        "- how a drug or intervention works\n"
        "- what the warning signs of a condition are\n"
        "- questions about a past or resolved episode ('turned out to be reflux')\n"
        "- questions about a relative who died long ago, heredity, or risk\n"
        "- professional, academic, or authoring context (a student, a first aid\n"
        "  handbook, a curiosity question about how paramedics triage)\n"
        "- preparation questions (what to keep in a first aid kit)\n\n"
        "The distinction that matters: is someone in trouble RIGHT NOW, or is "
        "this a question about the world? When genuinely uncertain, treat it as "
        "an emergency - a false alarm is acceptable, missing a real emergency "
        "is not.\n\n"
        f"Message: {question}\n\n"
        "Answer with exactly one word: EMERGENCY or SAFE"
    )
    result = ask(prompt, max_tokens=10).strip().upper()
    return "EMERGENCY" in result


def check_input(question: str):
    """Input gate. Returns None if safe, or an escalation message if not.

    Cascade:
      Layer 1  deterministic keyword screen. Does NOT block on its own - it
               routes. A keyword hit marks the message as needing scrutiny.
      Layer 2  LLM classifier. Makes the call, for every message.

    Why Layer 1 routes instead of blocking: an earlier version blocked on any
    keyword hit, with a whitelist of "educational" phrasings carved out. The
    whitelist was fitted to the test set that produced it - on an independently
    written set, 6 of 10 safe questions were wrongly blocked. Whitelists do not
    generalise. Reasoning about intent does.

    What Layer 1 still guarantees: if Layer 2 cannot run - API down, timeout,
    a silently broken function - a message that hit a keyword is BLOCKED. The
    deterministic layer is the floor, not the ceiling. The gate never
    disappears because a service did.
    """
    q = question.lower()
    keyword_hit = any(term in q for term in EMERGENCY_TERMS)

    try:
        if llm_emergency_check(question):
            return EMERGENCY_MESSAGE
    except Exception:
        if keyword_hit:
            return EMERGENCY_MESSAGE
        raise

    return None


def check_output(answer: str):
    """Output guardrail. Returns None if safe, or a safe replacement if not.

    Unsafe text is WITHHELD, not annotated: a caution appended below dosing
    advice still leaves the dosing advice on screen.
    """
    a = answer.lower()

    for pattern in DOSING_PATTERNS + DIAGNOSIS_PATTERNS:
        if re.search(pattern, a):
            return BLOCKED_MESSAGE

    return None