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
    """Layer 2 of the input cascade: catches what the keyword list misses."""
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
        "- academic or curiosity framing ('how long can a person survive...')\n\n"
        "A genuine question about general health, prevention, or how the body "
        "works is SAFE. Questions asking what the warning signs of a condition "
        "are, or how something is treated in a hospital, are SAFE - they seek "
        "knowledge, not help with an unfolding situation.\n\n"
        "When in doubt, treat it as an emergency. A false alarm is acceptable; "
        "missing a real emergency is not.\n\n"
        f"Message: {question}\n\n"
        "Answer with exactly one word: EMERGENCY or SAFE"
    )
    result = ask(prompt, max_tokens=10).strip().upper()
    return "EMERGENCY" in result


def check_input(question: str):
    """Input gate. Returns None if safe, or an escalation message if not.

    Cascade: deterministic keywords first (cannot hallucinate, cannot fail
    open), LLM classifier second for paraphrase and indirect framing.
    """
    q = question.lower()
    if any(term in q for term in EMERGENCY_TERMS):
        return EMERGENCY_MESSAGE
    if llm_emergency_check(question):
        return EMERGENCY_MESSAGE
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