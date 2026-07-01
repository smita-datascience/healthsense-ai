"""ORM models. One table now; this is where memory + eval data will live."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.database import Base


class Interaction(Base):
    """A single user query and the assistant's response.

    Doubles as: conversation history (memory), a risk audit trail (safety),
    and the raw material for offline evaluation later.
    """

    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=False, default="anonymous")
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    risk_level = Column(String(16), nullable=False, default="unknown")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
