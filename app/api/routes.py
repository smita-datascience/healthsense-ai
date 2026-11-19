"""API routes. Phase 0: a health check so we can confirm the app boots.
We'll add the /consult endpoint once the crew + memory + safety are wired.
"""
"""API routes for HealthSense AI."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.crew import answer

router = APIRouter()


class AskRequest(BaseModel):
    question: str


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok", "service": "HealthSense AI"}


@router.post("/ask")
def ask_endpoint(req: AskRequest):
    """Send a health question to the agent and return its answer."""
    try:
        return {"answer": answer(req.question)}
    except Exception:
        # Save the full error to a file, because CrewAI's long console
        # output pushes tracebacks out of the terminal.
        import datetime
        import traceback
        with open("ask_errors.log", "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.datetime.now()} | question: {req.question}\n")
            f.write(traceback.format_exc())
        raise