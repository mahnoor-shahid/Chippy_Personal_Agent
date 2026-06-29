"""WhatsApp front-end via Twilio.

Flow:
  Twilio POSTs your inbound message to /whatsapp
    -> we immediately return 200 (Twilio's webhook times out ~15s; the agent
       takes longer than that)
    -> the agent runs in the background
    -> the reply is pushed back via Twilio's REST API

The same `send_whatsapp()` helper is reused by the scheduler for the 7am digest.

Run locally:
    uvicorn src.agent.whatsapp:app --port 8000
    # then expose it:  ngrok http 8000
    # and point your Twilio sandbox "WHEN A MESSAGE COMES IN" webhook at
    #   https://<your-ngrok>.ngrok-free.app/whatsapp   (HTTP POST)
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response

from .brain import run_agent

load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
# Allowlist of WhatsApp numbers that may use Chippy (comma-separated). Scheduled
# briefings/posts are broadcast to all of them; replies go to the sender.
OWNERS = [n.strip() for n in os.getenv("MY_WHATSAPP_TO", "").split(",") if n.strip()]

# Validate Twilio's request signature (prevents spoofed webhooks). Off by default
# so first-time ngrok testing is frictionless; turn on once it works.
VALIDATE = os.getenv("TWILIO_VALIDATE", "false").lower() == "true"

WHATSAPP_MAX_LEN = 1500  # Twilio caps a WhatsApp message at 1600 chars

app = FastAPI(title="Personal Agent — WhatsApp")


def _twilio_client():
    from twilio.rest import Client

    if not (ACCOUNT_SID and AUTH_TOKEN):
        raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set in .env")
    return Client(ACCOUNT_SID, AUTH_TOKEN)


def send_whatsapp(text: str, to: str | None = None) -> None:
    """Clean Markdown -> WhatsApp formatting, then send (split if too long)."""
    from .wa_format import split_message, to_whatsapp

    client = _twilio_client()
    recipients = [to] if to else OWNERS  # explicit reply, or broadcast to all
    if not recipients:
        raise RuntimeError("No recipient: set MY_WHATSAPP_TO in .env or pass `to`.")
    parts = split_message(to_whatsapp(text), WHATSAPP_MAX_LEN)
    for recipient in recipients:
        for part in parts:
            client.messages.create(from_=FROM_NUMBER, to=recipient, body=part)


async def _handle_message(body: str, sender: str) -> None:
    from .limits import (
        DAILY_LIMIT,
        LIMIT_REACHED_MESSAGE,
        STATUS_MESSAGE,
        WARN_SUFFIX,
        check,
        is_status_request,
        remaining_today,
    )

    # Free quota check — doesn't count, doesn't call the LLM.
    if is_status_request(body):
        left = remaining_today(sender)
        send_whatsapp(STATUS_MESSAGE.format(remaining=left, limit=DAILY_LIMIT), to=sender)
        return

    # Daily message cap (per user).
    status = check(sender)
    if not status["allowed"]:
        send_whatsapp(LIMIT_REACHED_MESSAGE.format(limit=DAILY_LIMIT), to=sender)
        return

    try:
        # `sender` (e.g. "whatsapp:+9233...") is the per-user conversation key,
        # so each number keeps its own memory.
        reply = await run_agent(body, conversation_id=sender)
    except Exception as e:  # never leave the user hanging
        reply = f"Sorry — the agent hit an error: {type(e).__name__}: {e}"

    if status["warn"]:
        reply += WARN_SUFFIX.format(remaining=status["remaining"])

    send_whatsapp(reply, to=sender)


def _signature_ok(request: Request, form: dict) -> bool:
    if not VALIDATE:
        return True
    from twilio.request_validator import RequestValidator

    validator = RequestValidator(AUTH_TOKEN)
    # Must match the exact public URL Twilio called; override via PUBLIC_URL if
    # ngrok rewriting confuses request.url.
    url = os.getenv("PUBLIC_URL", "").strip() or str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(url, form, signature)


@app.get("/")
def health() -> dict:
    return {"status": "ok", "allowed_numbers": len(OWNERS), "signature_validation": VALIDATE}


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks) -> Response:
    form = dict(await request.form())

    if not _signature_ok(request, form):
        return Response(status_code=403)

    sender = (form.get("From") or "").strip()
    body = (form.get("Body") or "").strip()

    # Personal agent: silently ignore anyone not on the allowlist.
    if OWNERS and sender not in OWNERS:
        return Response(status_code=204)

    if body:
        background.add_task(_handle_message, body, sender)

    # Empty TwiML ack — the real reply arrives via REST when the agent finishes.
    return Response(content="", media_type="text/xml")
