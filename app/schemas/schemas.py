"""Request / response contracts for the API."""
from pydantic import BaseModel, Field


class ConsultRequest(BaseModel):
    user_id: str = Field(default="anonymous")
    query: str = Field(..., min_length=1, description="The user's health question.")


class ConsultResponse(BaseModel):
    response: str
    risk_level: str
    interaction_id: int
