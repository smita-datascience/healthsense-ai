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
   import re

# Educational framings: the user is asking ABOUT a condition, not reporting one.
# A keyword hit inside one of these does not block outright - it is routed to
# Layer 2 instead. The cascade is preserved; only the decision maker changes.
EDUCATIONAL_PATTERNS = [
    r"^what (are|is) the (warning )?signs?\b",
    r"^what (are|is) the symptoms?\b",
    r"^what does .{0,40}\b(stand for|mean)\b",
    r"^what is (a|an|the)\b",
    r"^why does .{0,60}\b(happen|occur)\b",
    r"^how (is|are) .{0,60}\b(treated|diagnosed|managed)\b",
    r"\b(last (week|month|year)|years? ago|used to)\b",   # resolved / past tense
]


def looks_educational(question: str) -> bool:
    q = question.lower().strip()
    return any(re.search(p, q) for p in EDUCATIONAL_PATTERNS)


def check_input(question: str):
    """Input gate. Returns None if safe, or an escalation message if not.

    Cascade:
      Layer 1  deterministic keyword screen. Cannot hallucinate, cannot fail
               open. Blocks immediately UNLESS the message reads as an
               educational question, in which case the decision is passed
               down to Layer 2 rather than skipped.
      Layer 2  LLM classifier. Handles paraphrase, indirect framing, and the
               educational cases Layer 1 deferred.

    Fail-safe: if Layer 2 cannot run (API down, timeout), a message that hit
    a keyword is BLOCKED. The gate never disappears because a service did.
    """
    q = question.lower()
    keyword_hit = any(term in q for term in EMERGENCY_TERMS)

    if keyword_hit and not looks_educational(question):
        return EMERGENCY_MESSAGE

    try:
        if llm_emergency_check(question):
            return EMERGENCY_MESSAGE
    except Exception:
        # Layer 2 unavailable. If Layer 1 saw something, block.
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