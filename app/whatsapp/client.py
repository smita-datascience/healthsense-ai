"""Send messages through the WhatsApp Cloud API, and download media users send."""
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


# Matches the report reader's limit; checked BEFORE downloading.
MAX_MEDIA_BYTES = 10 * 1024 * 1024


class MediaTooLarge(Exception):
    """The file is bigger than we are willing to download."""


def download_media(media_id: str) -> tuple[bytes, str]:
    """Fetch a file the user sent. Returns (bytes, mime_type).

    Meta's media download is two calls: the media ID gives a short-lived URL
    (valid ~5 minutes), and that URL - also needing the access token - gives
    the bytes. The file is kept in memory only, never written to disk.
    """
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    meta_url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{media_id}"
    info = httpx.get(meta_url, headers=headers, timeout=20)
    info.raise_for_status()
    info = info.json()
    if int(info.get("file_size") or 0) > MAX_MEDIA_BYTES:
        raise MediaTooLarge(info.get("file_size"))

    resp = httpx.get(info["url"], headers=headers, timeout=60)
    resp.raise_for_status()
    if len(resp.content) > MAX_MEDIA_BYTES:
        raise MediaTooLarge(len(resp.content))
    return resp.content, info.get("mime_type", "")
