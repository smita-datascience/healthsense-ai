"""Triage -> Explainer crew for HealthSense AI, with memory + guardrails."""
from crewai import Agent, Task, Crew, Process, LLM

from config.settings import settings
from app.memory.memory import recent_history, save_interaction
from app.agents.tools import search_health_knowledge
from app.safety.guardrails import check_input, check_output
from app.core.language import detect_language, to_english, from_english


# Agents are built FRESH for every question (see answer() below).
# CrewAI agent executors cannot be shared between requests running at the
# same time - a shared, module-level agent fails under concurrent load with
# "Executor is already running" (found by the Locust stress test).

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


def answer(question: str, user_id: str = "demo_user") -> str:
    """Run the triage -> explainer crew, with memory and guardrails.

    Multi-language flow - "English core, translation at the edges":
      detect language (rules)  ->  input gate on the ORIGINAL message
      ->  translate question to English  ->  crew runs in English
      ->  output guardrail on the ENGLISH answer  ->  translate answer back.
    The guardrail always reads English, the language its patterns are written
    in; translation happens only after the answer has passed it.
    """
    lang = detect_language(question)

    # INPUT GUARDRAIL: emergency check BEFORE the agent runs. Runs on the
    # original text - no translation step can drop or soften a symptom first.
    emergency = check_input(question, lang)
    if emergency:
        save_interaction(user_id, question, emergency)
        return emergency

    # The crew, retrieval and output guardrail all work in English.
    question_en = to_english(question) if lang != "en" else question

    history = recent_history(user_id, limit=3)
    history_block = f"\nRecent conversation:\n{history}\n" if history else ""

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
            "the question refers to something earlier. Do NOT answer the question."
        ),
        expected_output="A short assessment: topic, urgency, and what to focus on.",
        agent=triage_agent,
    )

    explain_task = Task(
        description=(
            f"{history_block}"
            f"First, use the search_health_knowledge tool to look up facts about: {question_en}\n"
            "Then, using the triage assessment and retrieved facts, write a "
            "plain-language answer. Base it on the retrieved facts. If the "
            "question refers to earlier conversation, use that context. Write "
            "the answer in English, even if the history is in another language "
            "- it is translated for the user after the safety check. End with "
            "one line reminding the user this is general information, not a "
            "diagnosis or medical advice."
        ),
        expected_output="A clear, friendly answer with a brief disclaimer.",
        agent=explainer_agent,
        context=[triage_task],
    )

    crew = Crew(
        agents=[triage_agent, explainer_agent],
        tasks=[triage_task, explain_task],
        process=Process.sequential,
        verbose=False,
    )
    result = str(crew.kickoff())

    # OUTPUT GUARDRAIL: on the English answer, before any translation.
    blocked = check_output(result, lang)
    if blocked:
        result = blocked
    elif lang != "en":
        try:
            translated = from_english(result, lang)
            # Second, cheap pass on the translation: number+unit patterns
            # ("500 mg") are the same in any script.
            result = check_output(translated, lang) or translated
        except Exception:
            pass  # translation failed: send the already-checked English answer
    save_interaction(user_id, question, result)
    return result