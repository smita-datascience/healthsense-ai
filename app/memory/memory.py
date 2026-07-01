"""Memory layer for HealthSense AI — buffer memory over the interactions table.

Save every turn; load the recent ones to feed back as context.
The context window is finite, so we keep only the last few turns (buffer).
"""
from app.db.database import SessionLocal
from app.db.models import Interaction


def save_interaction(user_id: str, question: str, answer: str) -> int:
    """Persist one Q&A turn. Returns the new row's id."""
    db = SessionLocal()
    try:
        row = Interaction(user_id=user_id, query=question, response=answer)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def recent_history(user_id: str, limit: int = 3) -> str:
    """Return the last `limit` turns for this user, formatted for a prompt.

    Empty string if there's no history yet (first message).
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Interaction)
            .filter(Interaction.user_id == user_id)
            .order_by(Interaction.id.desc())
            .limit(limit)
            .all()
        )
        rows = list(reversed(rows))  # oldest -> newest
        if not rows:
            return ""
        return "\n".join(f"User asked: {r.query}\nYou answered: {r.response}" for r in rows)
    finally:
        db.close()