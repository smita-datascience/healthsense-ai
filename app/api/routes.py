"""API routes for HealthSense AI."""
import datetime
import traceback
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.crew import answer

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    # Conversation memory is kept PER user_id. If a caller does not send one,
    # they get a fresh random id (no memory) - never a shared default, because
    # a shared id lets one user's health details appear in another user's
    # answer (found during the Locust stress test).
    user_id: str | None = Field(
        default=None,
        description="Optional. Send the same id on every message to keep a conversation's memory.",
    )


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok", "service": "HealthSense AI"}


@router.post("/ask")
def ask_endpoint(req: AskRequest):
    """Send a health question to the agent and return its answer."""
    user_id = req.user_id or f"anon-{uuid.uuid4()}"
    try:
        return {"answer": answer(req.question, user_id=user_id), "user_id": user_id}
    except Exception:
        # Save the full error to a file, because long console output can push
        # tracebacks out of the terminal.
        with open("ask_errors.log", "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.datetime.now()} | question: {req.question}\n")
            f.write(traceback.format_exc())
        raise