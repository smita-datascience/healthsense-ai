"""Safety guardrails for HealthSense AI - hybrid emergency detection."""
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


def llm_emergency_check(question: str) -> bool:
    prompt = (
        "You are a medical safety screen. Decide if the message describes a "
        "possible medical emergency needing immediate care such as severe chest "
        "pain, trouble breathing, signs of stroke, severe bleeding, suicidal "
        "thoughts, overdose, or loss of consciousness. When in doubt, treat it "
        "as an emergency - a false alarm is acceptable, missing a real "
        "emergency is not.\n\n"
        f"Message: {question}\n\n"
        "Answer with exactly one word: EMERGENCY or SAFE"
    )
    result = ask(prompt, max_tokens=10).strip().upper()
    return "EMERGENCY" in result


def check_input(question: str):
    q = question.lower()
    if any(term in q for term in EMERGENCY_TERMS):
        return EMERGENCY_MESSAGE
    if llm_emergency_check(question):
        return EMERGENCY_MESSAGE
    return None
def check_output(answer: str) -> str:
    """Output guardrail: screen the ANSWER before the user sees it.

    Catches two risks even a safe question can produce:
    - specific medication dosing
    - diagnostic language ('you have X')
    If found, append a stronger caution rather than blocking the answer.
    """
    a = answer.lower()

    dosing_terms = ["mg ", "milligram", "dosage", "take ", "tablets", "pills a day"]
    diagnosis_terms = ["you have", "you likely have", "you are suffering from", "diagnosis is"]

    flagged = any(t in a for t in dosing_terms) or any(t in a for t in diagnosis_terms)

    if flagged:
        return (
            answer
            + "\n\n**Important:** This response may touch on specific dosing or "
            "diagnosis. Do not act on it without confirming with a licensed "
            "healthcare professional — only they can advise on your situation."
        )
    return answer
