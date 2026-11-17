"""WhatsApp webhook: GET for Meta's one-time handshake, POST for messages.

Flow for a message:
  Meta --POST--> verify signature --> parse --> dedup --> 200 OK (fast)
                                                     \\--> background:
        text           -> crew.answer()             -> send_text()
        image / PDF    -> download -> explain_report() -> send_text()

We answer Meta immediately and do the slow crew run afterwards, because Meta
retries any delivery that isn't acknowledged quickly.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from config.settings import settings
from app.whatsapp.client import MediaTooLarge, download_media, send_text
from app.whatsapp.dedup import seen_messages
from app.whatsapp.security import pseudonymous_user_id, verify_signature

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])

FALLBACK_REPLY = (
    "Sorry, I couldn't process that just now. Please try again in a minute. "
    "If this is an emergency, call 112 or go to the nearest hospital."
)
NON_TEXT_REPLY = (
    "I can read typed messages, and lab reports sent as a photo or PDF. "
    "Please type your health question or send your report."
)
TOO_LARGE_REPLY = (
    "That file is too large for me to read (limit 10 MB). "
    "Please send a photo of the results page instead."
)
MEDIA_TYPES = {"image", "document"}


@router.get("")
def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta calls this once when you save the webhook URL. We echo the
    challenge only if the verify token matches the one we configured."""
    if (
        mode == "subscribe"
        and settings.whatsapp_verify_token
        and token == settings.whatsapp_verify_token
    ):
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Verification failed")


def extract_messages(payload: dict) -> list[dict]:
    """Pull user messages out of Meta's nested payload.

    Returns [{"id", "from", "type", "text", "media_id", "mime_type",
    "caption"}]. Status updates (sent/delivered/read receipts) arrive on the
    same webhook and are ignored here.
    """
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                media = msg.get(msg.get("type") or "") if msg.get("type") in MEDIA_TYPES else None
                media = media if isinstance(media, dict) else {}
                out.append(
                    {
                        "id": msg.get("id"),
                        "from": msg.get("from"),
                        "type": msg.get("type"),
                        "text": (msg.get("text") or {}).get("body", ""),
                        "media_id": media.get("id"),
                        "mime_type": media.get("mime_type", ""),
                        "caption": media.get("caption", ""),
                    }
                )
    return out


def process_message(msg: dict) -> None:
    """Runs after the 200 has gone back to Meta."""
    phone = msg["from"]
    try:
        if msg["type"] in MEDIA_TYPES and msg.get("media_id"):
            # Lab report: same safety gates, different front end.
            from app.agents.report import explain_report

            data, mime_type = download_media(msg["media_id"])
            reply = explain_report(
                data, mime_type or msg.get("mime_type", ""),
                caption=msg.get("caption", ""),
                user_id=pseudonymous_user_id(phone),
            )
        elif msg["type"] != "text" or not msg["text"].strip():
            reply = NON_TEXT_REPLY
        else:
            # Imported here so the webhook module (and its tests) load without
            # starting CrewAI. The crew -- including both safety gates -- runs
            # unchanged; the channel adds nothing in front of or behind it.
            from app.agents.crew import answer

            reply = answer(msg["text"], user_id=pseudonymous_user_id(phone))
    except MediaTooLarge:
        reply = TOO_LARGE_REPLY
    except Exception:
        log.exception("Crew failed for message %s", msg["id"])
        reply = FALLBACK_REPLY
    try:
        send_text(phone, reply)
    except Exception:
        log.exception("Could not deliver reply for message %s", msg["id"])


@router.post("")
async def receive_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw, signature, settings.whatsapp_app_secret):
        raise HTTPException(status_code=403, detail="Bad signature")

    payload = await request.json()
    for msg in extract_messages(payload):
        if msg["id"] and msg["from"] and seen_messages.first_time(msg["id"]):
            background.add_task(process_message, msg)
    return {"status": "received"}
