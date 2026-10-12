"""LLM factory for HealthSense AI.

Block 1 in code: this is the single point where we configure our connection
to the model. Every agent we build later will get its LLM from here, so any
change (model, temperature, provider) happens in ONE place.
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from config.settings import settings

load_dotenv()  # read .env so ANTHROPIC_API_KEY is available


def get_client() -> Anthropic:
    """Return a configured Anthropic client."""
    return Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def ask(prompt: str, max_tokens: int = 300) -> str:
    """Send one prompt to the model and return its text reply.

    Low temperature (0.2) on purpose: caution + consistency for a health
    assistant, and reliable, well-formed output. (Block 1: low temp = sharper
    distribution = the model stays on its most-confident path.)
    """
    client = get_client()
    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text