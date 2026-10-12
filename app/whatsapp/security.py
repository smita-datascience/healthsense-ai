"""Webhook authenticity checks.

Meta signs every webhook POST with HMAC-SHA256 over the *raw* request body,
keyed by the App Secret, and sends it in the `X-Hub-Signature-256` header as
`sha256=<hex>`. Anyone on the internet can POST to a public URL, so we reject
anything we can't verify.

Fail-closed: if the App Secret isn't configured, nothing verifies. A missing
secret must never turn the check off.
"""
import hashlib
import hmac


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    # Constant-time compare so timing can't leak how many characters matched.
    return hmac.compare_digest(expected, received)


def pseudonymous_user_id(phone: str) -> str:
    """Stable user id for memory, without storing the raw phone number.

    The conversation table keeps health questions; pairing them with a raw
    phone number would turn a log into personal health data. We still need the
    real number to reply, but only in memory for the duration of the request.
    """
    return "wa_" + hashlib.sha256(phone.encode()).hexdigest()[:16]
