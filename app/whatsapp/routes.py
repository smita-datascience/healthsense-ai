"""WhatsApp webhook: GET for Meta's one-time handshake, POST for messages.

Flow for a message:
  Meta --POST--> verify signature --> parse --> dedup --> 200 OK (fast)
                                                     \\--> background:
        text           -> crew.answer()             -> send_text()
        image / PDF    -> download -> explain_report() -> send_text()
        voice note     -> download -> transcribe -> crew.answer() -> send_text()

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
    "I can read typed messages, voice notes, and lab reports sent as a photo "
    "or PDF. Please type or record your health question, or send your report."
)
TOO_LARGE_REPLY = (
    "That file is too large for me to read (limit 10 MB). "
    "Please send a photo of the results page instead."
)
AUDIO_FORMAT_REPLY = (
    "Sorry, I couldn't play that audio format. Please hold the microphone "
    "button in WhatsApp to record a voice note, or type your question. "
    "If this is an emergency, call 112 or go to the nearest hospital."
)
EMPTY_AUDIO_REPLY = (
    "Sorry, I couldn't hear anything in that voice note. Please try again in "
    "a quieter place, or type your question. "
    "If this is an emergency, call 112 or go to the nearest hospital."
)
MEDIA_TYPES = {"image", "document"}
AUDIO_TYPES = {"audio"}


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
                mtype = msg.get("type") or ""
                media = msg.get(mtype) if mtype in MEDIA_TYPES | AUDIO_TYPES else None
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


def _answer_voice_note(msg: dict, user_id: str) -> str:
    """Voice note -> text -> the SAME answer() path as a typed message.

    The transcript is shown back to the user ("what I heard") so a misheard
    word is visible straight away - in health, one wrong word can change the
    meaning. The input safety gate runs on the transcript, exactly as it runs
    on typed text.
    """
    from app.core.speech import transcribe
    from app.agents.crew import answer

    data, mime_type = download_media(msg["media_id"])
    heard = transcribe(data, mime_type or msg.get("mime_type", ""))
    reply = answer(heard, user_id=user_id)
    return f'🎤 "{heard}"\n\n{reply}'


def process_message(msg: dict) -> None:
    """Runs after the 200 has gone back to Meta."""
    from app.core.speech import EmptyTranscript, UnsupportedAudio

    phone = msg["from"]
    user_id = pseudonymous_user_id(phone)
    try:
        if msg["type"] in MEDIA_TYPES and msg.get("media_id"):
            # Lab report: same safety gates, different front end.
            from app.agents.report import explain_report

            data, mime_type = download_media(msg["media_id"])
            reply = explain_report(
                data, mime_type or msg.get("mime_type", ""),
                caption=msg.get("caption", ""),
                user_id=user_id,
            )
        elif msg["type"] in AUDIO_TYPES and msg.get("media_id"):
            # Voice note: transcribe, then the typed-message path, unchanged.
            reply = _answer_voice_note(msg, user_id)
        elif msg["type"] != "text" or not msg["text"].strip():
            reply = NON_TEXT_REPLY
        else:
            # Imported here so the webhook module (and its tests) load without
            # starting CrewAI. The crew -- including both safety gates -- runs
            # unchanged; the channel adds nothing in front of or behind it.
            from app.agents.crew import answer

            reply = answer(msg["text"], user_id=user_id)
    except MediaTooLarge:
        reply = TOO_LARGE_REPLY
    except UnsupportedAudio:
        reply = AUDIO_FORMAT_REPLY
    except EmptyTranscript:
        reply = EMPTY_AUDIO_REPLY
    except Exception:
        log.exception("Processing failed for message %s", msg["id"])
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