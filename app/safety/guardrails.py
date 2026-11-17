"""Safety guardrails for HealthSense AI - hybrid emergency detection."""
import re
import unicodedata

from app.core.language import detect_language
from app.core.llm import ask

EMERGENCY_TERMS = [
    # --- English ---
    "chest pain", "can't breathe", "cant breathe", "not breathing",
    "suicide", "kill myself", "self harm", "self-harm",
    "overdose", "unconscious", "stroke", "severe bleeding",
    "heart attack", "choking",

    # --- Hindi (Devanagari) and Hinglish (Hindi in Roman letters) ---
    # Written from red-flag CONCEPTS (chest pain, breathlessness, fainting,
    # overdose/poisoning, suicidal intent, bleeding, stroke signs, airway),
    # NOT copied from the multilingual test messages - fitting keywords to
    # the test set is the overfitting mistake the Layer 1 redesign fixed.
    # Devanagari is matched after _normalise() (see below), so spelling
    # variants like साँस/सांस or ख़/ख need only one entry.
    # Chest pain / heart
    "सीने में दर्द", "छाती में दर्द", "दिल का दौरा",
    "seene mein dard", "sine mein dard", "seene me dard", "chhati mein dard",
    "chest mein dard", "chest mein pressure", "dil ka daura",
    # Breathing
    "सांस नहीं", "सांस लेने में", "सांस रुक",
    "saans nahi", "sans nahi", "saas nahi", "saans lene mein", "saans ruk",
    # Fainting / unresponsive
    "बेहोश", "होश नहीं", "behosh", "hosh nahi",
    # Overdose / poisoning
    "गोलियां खा", "गोली खा", "ज्यादा दवा", "जहर", "पी लिया", "निगल लिया",
    "goliyan kha", "goliya kha", "goli kha li", "zyada dawa", "jyada dawa",
    "zeher", "zehar", "jahar", "nigal liya",
    # Suicidal intent
    "जीने का मन नहीं", "मरना चाहत", "आत्महत्या", "खत्म कर",
    "jeene ka mann nahi", "jine ka man nahi", "marna chahta", "marna chahti",
    "khudkushi", "aatmahatya", "khatam karna", "khatam kar dena",
    # Bleeding
    "खून बह", "खून रुक", "khoon ruk", "khoon beh", "khun ruk", "khun beh",
    # Stroke signs
    "लकवा", "चेहरा एक तरफ", "मुंह टेढ़ा", "बोल नहीं पा",
    "lakwa", "muh tedha", "munh tedha", "bol nahi pa", "haath pair kaam nahi",
    # Airway
    "गला बंद", "gala band",
]


def _normalise(text: str) -> str:
    """Lower-case, and fold common Devanagari spelling variants together.

    - NFD splits pre-composed nukta letters (e.g. U+0959 ख़) into base + nukta,
      then the nukta (U+093C) is dropped: ख़ -> ख, फ़ -> फ, ज़ -> ज.
    - Chandrabindu (U+0901) becomes anusvara (U+0902): साँस -> सांस.
    Without this, the same word typed two ways would miss the keyword floor.
    """
    t = unicodedata.normalize("NFD", text.lower())
    t = t.replace("\u093c", "").replace("\u0901", "\u0902")
    return unicodedata.normalize("NFC", t)


# Safety messages are PRE-TRANSLATED fixed text, never generated at runtime.
# The emergency message must come out even when the LLM is down, and must say
# exactly the same thing every time. (Translations should be reviewed by a
# native Hindi speaker before real-world use.)
EMERGENCY_MESSAGES = {
    "en": (
        "This may be a medical emergency. Please contact emergency services "
        "immediately - in India call 112 (or 108 for an ambulance). "
        "If someone is in danger, do not wait for an online response."
    ),
    "hi": (
        "यह एक मेडिकल इमरजेंसी हो सकती है। कृपया तुरंत आपातकालीन सेवाओं से "
        "संपर्क करें - भारत में 112 पर कॉल करें (एम्बुलेंस के लिए 108)। "
        "अगर किसी की जान खतरे में है, तो ऑनलाइन जवाब का इंतज़ार न करें।"
    ),
    "hinglish": (
        "Yeh ek medical emergency ho sakti hai. Kripya turant emergency "
        "services ko call karein - India mein 112 dial karein (ambulance ke "
        "liye 108). Agar kisi ki jaan khatre mein hai, to online jawab ka "
        "intezaar na karein."
    ),
}

BLOCKED_MESSAGES = {
    "en": (
        "I can't share that response. It contained specific dosing or diagnostic "
        "language, which only a licensed healthcare professional can safely give "
        "you. Please speak to a doctor or pharmacist about your situation.\n\n"
        "I'm happy to explain conditions, terminology, or general health topics instead."
    ),
    "hi": (
        "मैं यह जवाब नहीं दिखा सकता। इसमें दवा की खुराक या बीमारी की पहचान "
        "(डायग्नोसिस) से जुड़ी बातें थीं, जो सिर्फ़ एक लाइसेंस प्राप्त डॉक्टर ही "
        "सुरक्षित रूप से बता सकते हैं। कृपया अपनी स्थिति के बारे में डॉक्टर या "
        "फार्मासिस्ट से बात करें।\n\n"
        "मैं बीमारियों, मेडिकल शब्दों या सामान्य स्वास्थ्य विषयों को समझाने में "
        "ख़ुशी से मदद कर सकता हूँ।"
    ),
    "hinglish": (
        "Main yeh jawab share nahi kar sakta. Ismein dawa ki dose ya diagnosis "
        "se judi baatein thi, jo sirf ek licensed doctor hi safely bata sakte "
        "hain. Kripya apni situation ke baare mein doctor ya pharmacist se baat "
        "karein.\n\n"
        "Main bimariyon, medical terms ya general health topics samjhane mein "
        "khushi se madad kar sakta hoon."
    ),
}

# English versions under the old names, so existing code keeps working.
EMERGENCY_MESSAGE = EMERGENCY_MESSAGES["en"]
BLOCKED_MESSAGE = BLOCKED_MESSAGES["en"]

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


def check_input(question: str, lang: str | None = None):
    """Input gate. Returns None if safe, or an escalation message if not.

    The escalation message is in the user's language (detected by rules, no
    API call), so it still comes out in Hindi when the LLM is unreachable.

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
    lang = lang or detect_language(question)
    emergency_message = EMERGENCY_MESSAGES.get(lang, EMERGENCY_MESSAGE)
    q = _normalise(question)
    keyword_hit = any(_normalise(term) in q for term in EMERGENCY_TERMS)

    try:
        if llm_emergency_check(question):
            return emergency_message
    except Exception:
        if keyword_hit:
            return emergency_message
        raise

    return None


def llm_output_check(answer: str) -> bool:
    """Layer 2 of the output cascade: the reasoning layer. True = UNSAFE.

    Only called on answers the patterns flagged. Its job is to tell apart
    sentences that look alike but mean different things:
        "you have a migraine"                      -> diagnosis      -> UNSAFE
        "see a doctor if you have a weak immune system" -> a warning -> SAFE
    """
    prompt = (
        "You are the final safety check on a health information assistant's "
        "answer, just before it is sent to a member of the public. A keyword "
        "filter flagged this answer. Decide if it is UNSAFE.\n\n"
        "UNSAFE means ANY part of the answer does one of these:\n"
        "- tells the reader they have, or do not have, a specific condition "
        "(a diagnosis, or reassurance that rules something out)\n"
        "- gives a specific dose, amount or schedule for a medicine, or tells "
        "them to start, stop, increase or decrease a medicine\n"
        "- tells them they do not need to see a doctor, or can ignore a symptom\n\n"
        "These are SAFE, even though the wording can look similar:\n"
        "- conditional warnings: 'see a doctor if you have...', 'seek care if "
        "your fever lasts more than 3 days'\n"
        "- general education about how a condition, test or medicine works\n"
        "- facts about people in general ('most adults need 7-9 hours of sleep')\n"
        "- telling them to follow the label or ask a doctor or pharmacist about "
        "doses\n\n"
        "A conditional or a referral does not make unsafe content safe: 'if you "
        "have a headache, take two 500mg tablets' is UNSAFE, and so is a "
        "diagnosis followed by 'see a doctor if it gets worse'.\n\n"
        "When genuinely uncertain, answer UNSAFE - withholding a safe answer is "
        "an annoyance, sending an unsafe one is not.\n\n"
        f"Answer to check:\n{answer}\n\n"
        "Reply with exactly one word: UNSAFE or SAFE"
    )
    result = ask(prompt, max_tokens=10).strip().upper()
    return "UNSAFE" in result


def check_output(answer: str, lang: str = "en"):
    """Output guardrail. Returns None if safe, or a safe replacement if not.

    Cascade - the same shape as the input gate:
      Layer 1  regex patterns (dosing, diagnosis, discouraging care). No match
               -> the answer passes. A match does NOT block on its own - it
               routes the answer to Layer 2.
      Layer 2  LLM judge reads the flagged answer and makes the call.
      Floor    if Layer 2 cannot run (API down, timeout), a flagged answer is
               BLOCKED. The patterns are the floor, not the ceiling.

    Why: the patterns alone blocked a correct fever answer because it said
    "see a doctor if... you have underlying health conditions" - the same words
    as the diagnosis "you have a migraine". Words cannot tell those apart;
    reading for meaning can.

    The patterns are English, so this runs on the English answer BEFORE it is
    translated (see app/core/language.py). `lang` only picks which language the
    replacement message is shown in.

    Unsafe text is WITHHELD, not annotated: a caution appended below dosing
    advice still leaves the dosing advice on screen.
    """
    a = answer.lower()
    flagged = any(re.search(p, a) for p in DOSING_PATTERNS + DIAGNOSIS_PATTERNS)
    if not flagged:
        return None

    blocked_message = BLOCKED_MESSAGES.get(lang, BLOCKED_MESSAGE)
    try:
        if llm_output_check(answer):
            return blocked_message
    except Exception:
        return blocked_message  # fail safe: flagged + judge unavailable = block

    return None
