"""LLM factory for HealthSense AI.

Block 1 in code: this is the single point where we configure our connection
to the model. Every agent we build later will get its LLM from here, so any
change (model, temperature, provider) happens in ONE place.
"""
import base64
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

    No temperature is set: the Anthropic Python SDK this project uses (2.x)
    has no temperature argument on messages.create - passing one raises a
    TypeError. (An earlier comment here claimed "temperature 0.2"; the code
    never set it.) So LLM verdicts can vary slightly between runs: run the
    safety evals more than once before quoting a number.
    """
    client = get_client()
    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def ask_with_file(prompt: str, data: bytes, mime_type: str, max_tokens: int = 1500) -> str:
    """Send one prompt plus one image or PDF to the model; return its text.

    Used by the report reader. Images go as an "image" block, PDFs as a
    "document" block - the model reads both directly, no separate OCR step.
    """
    encoded = base64.standard_b64encode(data).decode("ascii")
    kind = "document" if mime_type == "application/pdf" else "image"
    client = get_client()
    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [
                {"type": kind, "source": {"type": "base64", "media_type": mime_type, "data": encoded}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return message.content[0].text
