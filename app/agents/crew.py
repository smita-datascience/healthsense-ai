"""Triage -> Explainer crew for HealthSense AI, with conversation memory.

Block 1: the LLM call (low temperature).
Block 2: each Agent is a ReAct agent (role + goal + backstory = its prompt).
Block 3: Task + Crew + Process.sequential coordinate the two agents.
Memory: load recent turns as context, save each turn after answering.
"""
from crewai import Agent, Task, Crew, Process, LLM

from config.settings import settings
from app.memory.memory import recent_history, save_interaction
from app.agents.tools import search_health_knowledge
from app.safety.guardrails import check_input

# Shared LLM. Low temperature (0.2): caution + consistency + clean output.
llm = LLM(
    model=f"anthropic/{settings.llm_model}",
    temperature=0.2,
)

# --- Agent 1: TRIAGE — assess the question ---
triage_agent = Agent(
    role="Health Triage Specialist",
    goal="Assess what a health question is really asking and how urgent it is.",
    backstory=(
        "A careful triage nurse. You quickly classify a question: what topic it "
        "covers, how urgent it seems, and what the answer should focus on. You "
        "never answer the question yourself — you only assess it."
    ),
    llm=llm,
    verbose=True,
)

# --- Agent 2: EXPLAINER — write the answer ---
explainer_agent = Agent(
    role="Health Information Explainer",
    goal="Write a clear, cautious, plain-language answer using the triage assessment.",
    backstory=(
        "A health-literacy expert. You take the triage specialist's assessment "
        "and turn it into a simple, friendly explanation. You never diagnose and "
        "always recommend professional care for anything specific or serious."
    ),
    llm=llm,
    tools=[search_health_knowledge],
    verbose=True,
)


def answer(question: str, user_id: str = "demo_user") -> str:
    """Run the triage -> explainer crew, with conversation memory."""
    emergency = check_input(question)
    if emergency:
        save_interaction(user_id, question, emergency)
        return emergency
    # 1. Load recent conversation history (buffer memory)
    history = recent_history(user_id, limit=3)
    history_block = f"\nRecent conversation:\n{history}\n" if history else ""

    # 2. Triage assesses, aware of prior context
    triage_task = Task(
        description=(
            f"{history_block}"
            f"Assess this health question: {question}\n"
            "State: the main topic, how urgent it seems (low/medium/high), and "
            "what a good answer should focus on. Use the conversation history if "
            "the question refers to something earlier. Do NOT answer the question."
        ),
        expected_output="A short assessment: topic, urgency, and what to focus on.",
        agent=triage_agent,
    )

    # 3. Explainer answers, using triage assessment + history
    explain_task = Task(
        description=(
            f"{history_block}"
            f"First, use the search_health_knowledge tool to look up facts about: {question}\n"
            "Then, using the triage assessment and the retrieved facts, write a "
            "plain-language answer. Base your answer on the retrieved facts. "
            "If the question refers to earlier conversation, use that context. "
            "End with one line reminding the user this is general information, "
            "not a diagnosis or medical advice."
        ),
        expected_output="A clear, friendly answer with a brief disclaimer.",
        agent=explainer_agent,
        context=[triage_task],
    )

    # 4. Coordinate the two agents in sequence
    crew = Crew(
        agents=[triage_agent, explainer_agent],
        tasks=[triage_task, explain_task],
        process=Process.sequential,
        verbose=True,
        
    )
    result = str(crew.kickoff())

    # 5. Save this turn so the next question can see it
    save_interaction(user_id, question, result)
    return result