"""Triage -> Explainer crew for HealthSense AI, with memory + guardrails."""
import datetime
import os
import threading
import time
import traceback
from contextlib import contextmanager

from crewai import Agent, Task, Crew, Process, LLM

from config.settings import settings
from app.memory.memory import recent_history, save_interaction
from app.agents.tools import search_health_knowledge
from app.safety.guardrails import (
    check_input,
    check_output,
    UNAVAILABLE_MESSAGES,
    UNAVAILABLE_MESSAGE,
)
from app.core.language import detect_language, to_english, from_english


# ---------------------------------------------------------------------------
# Timing (Locust stress test follow-up): measure each stage of a request so
# we speed up the step that is actually slow, not the one we guess is slow.
# One line per request goes to the console and to timings.csv.
# ---------------------------------------------------------------------------
TIMINGS_FILE = "timings.csv"
STAGES = ["input_gate", "translate_in", "crew", "output_gate", "translate_out"]
_timings_lock = threading.Lock()  # requests run in parallel threads


@contextmanager
def _timed(timings: dict, stage: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[stage] = time.perf_counter() - start


def _record_timings(timings: dict, lang: str, outcome: str, total: float) -> None:
    parts = " ".join(f"{s}={timings[s]:.1f}s" for s in STAGES if s in timings)
    print(f"[timing] lang={lang} outcome={outcome} {parts} total={total:.1f}s", flush=True)

    row = [datetime.datetime.now().isoformat(timespec="seconds"), lang, outcome]
    row += [f"{timings[s]:.2f}" if s in timings else "" for s in STAGES]
    row.append(f"{total:.2f}")
    with _timings_lock:
        new_file = not os.path.exists(TIMINGS_FILE)
        with open(TIMINGS_FILE, "a", encoding="utf-8") as f:
            if new_file:
                f.write(",".join(["time", "lang", "outcome", *STAGES, "total"]) + "\n")
            f.write(",".join(row) + "\n")


def _log_failure(stage: str, question: str) -> None:
    """Save the full error, because the user only sees the fixed message."""
    with open("ask_errors.log", "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.datetime.now()} | stage: {stage} | question: {question}\n")
        f.write(traceback.format_exc())


# ---------------------------------------------------------------------------
# Agents are built FRESH for every question (see answer() below).
# CrewAI agent executors cannot be shared between requests running at the
# same time - a shared, module-level agent fails under concurrent load with
# "Executor is already running" (found by the Locust stress test).
# ---------------------------------------------------------------------------
def make_llm() -> LLM:
    return LLM(model=f"anthropic/{settings.llm_model}")


def make_triage_agent(llm: LLM) -> Agent:
    return Agent(
        role="Health Triage Specialist",
        goal="Assess what a health question is really asking and how urgent it is.",
        backstory=(
            "A careful triage nurse. You classify a question: topic, urgency, and "
            "what the answer should focus on. You never answer it - only assess it."
        ),
        llm=llm,
        verbose=False,
    )


def make_explainer_agent(llm: LLM) -> Agent:
    return Agent(
        role="Health Information Explainer",
        goal="Write a clear, cautious, plain-language answer using the triage assessment.",
        backstory=(
            "A health-literacy expert. You take the triage assessment and write a "
            "simple explanation. You never diagnose and always recommend "
            "professional care for anything specific or serious."
        ),
        llm=llm,
        tools=[search_health_knowledge],
        verbose=False,
    )


def _run_crew(question_en: str, history_block: str) -> str:
    # Fresh agents for THIS question only - safe under concurrent requests.
    llm = make_llm()
    triage_agent = make_triage_agent(llm)
    explainer_agent = make_explainer_agent(llm)

    triage_task = Task(
        description=(
            f"{history_block}"
            f"Assess this health question: {question_en}\n"
            "State the main topic, how urgent it seems (low/medium/high), and "
            "what a good answer should focus on. Use the conversation history if "
            "the question refers to something earlier. Do NOT answer the question. "
            "Keep it to 3 short lines."
        ),
        expected_output="Three short lines: topic, urgency, and what to focus on.",
        agent=triage_agent,
    )

    # Answer length (timing follow-up): the crew was ~93% of request time and
    # translating long answers back to Hindi/Hinglish took ~20 s. Answers are
    # read on WhatsApp, so they are kept phone-sized: shorter to generate,
    # shorter to translate, easier to read.
    explain_task = Task(
        description=(
            f"{history_block}"
            f"First, use the search_health_knowledge tool to look up facts about: {question_en}\n"
            "Then, using the triage assessment and retrieved facts, write a "
            "plain-language answer. Base it on the retrieved facts. If the "
            "question refers to earlier conversation, use that context. Write "
            "the answer in English, even if the history is in another language "
            "- it is translated for the user after the safety check.\n\n"
            "The answer is read on a phone in WhatsApp, so keep it short: about "
            "150-200 words. Start with one or two plain sentences, then at most "
            "5 short bullet points. No headings, no tables. Include when to see "
            "a doctor if it matters for this question. End with one line "
            "reminding the user this is general information, not a diagnosis or "
            "medical advice."
        ),
        expected_output=(
            "A short, friendly WhatsApp-sized answer (about 150-200 words) with a "
            "brief disclaimer as the last line."
        ),
        agent=explainer_agent,
        context=[triage_task],
    )

    crew = Crew(
        agents=[triage_agent, explainer_agent],
        tasks=[triage_task, explain_task],
        process=Process.sequential,
        verbose=False,
    )
    return str(crew.kickoff())


def answer(question: str, user_id: str = "demo_user") -> str:
    """Run the triage -> explainer crew, with memory and guardrails.

    Multi-language flow - "English core, translation at the edges":
      detect language (rules)  ->  input gate on the ORIGINAL message
      ->  translate question to English  ->  crew runs in English
      ->  output guardrail on the ENGLISH answer  ->  translate answer back.
    The guardrail always reads English, the language its patterns are written
    in; translation happens only after the answer has passed it.

    Never silence: if the LLM service is unreachable (outage, credits, rate
    limit) the user gets a fixed, pre-translated UNAVAILABLE message that still
    gives the emergency numbers - never an HTTP 500 or an empty WhatsApp reply.
    """
    t0 = time.perf_counter()
    timings: dict = {}
    lang = detect_language(question)
    unavailable = UNAVAILABLE_MESSAGES.get(lang, UNAVAILABLE_MESSAGE)

    # INPUT GUARDRAIL: emergency check BEFORE the agent runs. Runs on the
    # original text - no translation step can drop or soften a symptom first.
    # If the LLM classifier is down, check_input still blocks keyword hits
    # (the floor); otherwise it re-raises and we send the UNAVAILABLE message.
    try:
        with _timed(timings, "input_gate"):
            emergency = check_input(question, lang)
    except Exception:
        _log_failure("input_gate", question)
        _record_timings(timings, lang, "unavailable", time.perf_counter() - t0)
        return unavailable

    if emergency:
        save_interaction(user_id, question, emergency)
        _record_timings(timings, lang, "emergency", time.perf_counter() - t0)
        return emergency

    history = recent_history(user_id, limit=3)
    history_block = f"\nRecent conversation:\n{history}\n" if history else ""

    # The crew, retrieval and output guardrail all work in English.
    try:
        with _timed(timings, "translate_in"):
            question_en = to_english(question) if lang != "en" else question
        with _timed(timings, "crew"):
            result = _run_crew(question_en, history_block)
    except Exception:
        _log_failure("crew", question)
        _record_timings(timings, lang, "unavailable", time.perf_counter() - t0)
        return unavailable

    # OUTPUT GUARDRAIL: on the English answer, before any translation.
    # check_output is already fail-safe (flagged + judge down = blocked).
    with _timed(timings, "output_gate"):
        blocked = check_output(result, lang)
    outcome = "answered"
    if blocked:
        result = blocked
        outcome = "blocked"
    elif lang != "en":
        try:
            with _timed(timings, "translate_out"):
                translated = from_english(result, lang)
                # Second, cheap pass on the translation: number+unit patterns
                # ("500 mg") are the same in any script.
                result = check_output(translated, lang) or translated
        except Exception:
            pass  # translation failed: send the already-checked English answer

    save_interaction(user_id, question, result)
    _record_timings(timings, lang, outcome, time.perf_counter() - t0)
    return result