"""Triage -> Explainer crew for HealthSense AI, with memory + guardrails."""
from crewai import Agent, Task, Crew, Process, LLM

from config.settings import settings
from app.memory.memory import recent_history, save_interaction
from app.agents.tools import search_health_knowledge
from app.safety.guardrails import check_input, check_output

llm = LLM(model=f"anthropic/{settings.llm_model}", temperature=0.2)

triage_agent = Agent(
    role="Health Triage Specialist",
    goal="Assess what a health question is really asking and how urgent it is.",
    backstory=(
        "A careful triage nurse. You classify a question: topic, urgency, and "
        "what the answer should focus on. You never answer it - only assess it."
    ),
    llm=llm,
    verbose=True,
)

explainer_agent = Agent(
    role="Health Information Explainer",
    goal="Write a clear, cautious, plain-language answer using the triage assessment.",
    backstory=(
        "A health-literacy expert. You take the triage assessment and write a "
        "simple explanation. You never diagnose and always recommend "
        "professional care for anything specific or serious."
    ),
    llm=llm,
    tools=[search_health_knowledge],
    verbose=True,
)


def answer(question: str, user_id: str = "demo_user") -> str:
    """Run the triage -> explainer crew, with memory and guardrails."""
    # INPUT GUARDRAIL: emergency check BEFORE the agent runs
    emergency = check_input(question)
    if emergency:
        save_interaction(user_id, question, emergency)
        return emergency

    history = recent_history(user_id, limit=3)
    history_block = f"\nRecent conversation:\n{history}\n" if history else ""

    triage_task = Task(
        description=(
            f"{history_block}"
            f"Assess this health question: {question}\n"
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
            f"First, use the search_health_knowledge tool to look up facts about: {question}\n"
            "Then, using the triage assessment and retrieved facts, write a "
            "plain-language answer. Base it on the retrieved facts. If the "
            "question refers to earlier conversation, use that context. End with "
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
        verbose=True,
    )
    result = str(crew.kickoff())

    blocked = check_output(result)
    if blocked:
        result = blocked
    save_interaction(user_id, question, result)
    return result
