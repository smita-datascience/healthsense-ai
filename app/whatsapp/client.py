"""Send messages through the WhatsApp Cloud API."""
import logging

import httpx

from config.settings import settings

log = logging.getLogger(__name__)

# WhatsApp rejects text bodies over 4096 characters.
MAX_TEXT = 4096


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Split a long answer into WhatsApp-sized chunks, preferring paragraph,
    then line, then word boundaries so no sentence is cut mid-word."""
    chunks, rest = [], text.strip()
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


def send_text(to: str, body: str) -> None:
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    for chunk in split_text(body):
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": chunk, "preview_url": False},
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=20)
        if resp.status_code >= 400:
            # Log Meta's error body (it explains expired tokens, unverified
            # recipients, etc.) but never the token itself.
            log.error("WhatsApp send failed %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
