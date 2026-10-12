# HealthSense AI v2 — WhatsApp channel

v2 adds a delivery channel, not a new brain. WhatsApp messages reach the same
`answer(question, user_id)` function the `/ask` API uses, so both safety gates
(`check_input`, `check_output`) run exactly as they do in v1 and the eval
numbers still describe what users get.

## Flow

```
User's WhatsApp
      |
      v
Meta Cloud API ──POST /webhook/whatsapp──> FastAPI
                                             1. verify X-Hub-Signature-256 (fail-closed)
                                             2. extract text messages, ignore status receipts
                                             3. drop duplicate message ids
                                             4. return 200 immediately
                                             5. background: crew.answer() -> send_text()
                                                    (gate 1 -> triage -> explainer -> gate 2)
```

## Design decisions

| Decision | Why |
|---|---|
| Reply 200 before running the crew | Meta retries slow acknowledgements; the crew takes seconds. |
| Signature check fails closed | A public URL accepts POSTs from anyone. A missing App Secret must reject everything, never skip the check. Same stance as the safety gate's deterministic floor. |
| Dedup on WhatsApp message id | Retries would otherwise produce two answers and two paid LLM runs. |
| Pseudonymous user id (`wa_` + SHA-256 prefix of the phone number) | The interactions table holds health questions. Keyed by raw phone numbers it becomes personal health data. The real number is used only in memory, to send the reply. |
| Crew failure sends a fixed fallback with emergency guidance | The user never gets silence; the fallback never contains model output. |
| Non-text messages get a polite "text only for now" | Images, voice and documents are later v2 work (report-analysis agent, voice I/O). |
| Long answers split at paragraph/word boundaries | WhatsApp rejects text bodies over 4096 characters. |

## Known limits (deliberately not solved yet)

- **BackgroundTasks, not a queue.** If the server restarts mid-answer, that answer is lost. Next hardening step: a durable queue (e.g. Redis + RQ/Celery, or a SQLite jobs table).
- **In-memory dedup.** Lost on restart, not shared between workers. Fix arrives with the queue: unique constraint on message id.
- **Temporary access token** expires in ~24 h. For anything beyond a demo, create a System User token in Meta Business settings.
- **Test number only** reaches up to 5 verified recipient numbers; real users need production setup and business verification.

## Configuration

`.env` (values from the Meta developer dashboard; never commit them):

```
WHATSAPP_ACCESS_TOKEN=      # WhatsApp > API Setup
WHATSAPP_PHONE_NUMBER_ID=   # WhatsApp > API Setup
WHATSAPP_APP_SECRET=        # App settings > Basic
WHATSAPP_VERIFY_TOKEN=      # any password you invent; same text goes into Meta's webhook form
WHATSAPP_API_VERSION=v25.0
```

## Tests

```
python -m pytest tests/test_whatsapp.py -v
```

12 tests, no network and no LLM: handshake accept/reject, signature valid/tampered/missing/unconfigured, unsigned POST never reaches the crew, pseudonymous id, duplicate delivery answered once, status receipts ignored, non-text reply, crew failure fallback, message splitting.
