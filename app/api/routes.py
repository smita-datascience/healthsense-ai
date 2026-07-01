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
    return {"answer": answer(req.question)}
