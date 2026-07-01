"""Safety guardrails for HealthSense AI — deterministic checks around the model.

Input guardrail: detect emergencies BEFORE the agent runs, and route to real
help instead of answering. This is a keyword stub; production would use a
trained classifier + a framework like NeMo Guardrails.
"""

EMERGENCY_TERMS = [
    "chest pain", "can't breathe", "cant breathe", "not breathing",
    "suicide", "kill myself", "self harm", "self-harm",
    "overdose", "unconscious", "stroke", "severe bleeding",
    "heart attack", "choking",
]

EMERGENCY_MESSAGE = (
    "⚠️ This may be a medical emergency. Please contact emergency services "
    "immediately — in India call 112 (or 108 for an ambulance). "
    "If someone is in danger, do not wait for an online response."
)


def check_input(question: str) -> str | None:
    """Return an emergency message if the input looks urgent, else None.

    None means 'safe to proceed to the agent'.
    """
    q = question.lower()
    if any(term in q for term in EMERGENCY_TERMS):
        return EMERGENCY_MESSAGE
    return None