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
import random
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response

from . import storage
from .brain import run_agent

load_dotenv()

# Snarky "welcome back" if the user returns after being away this many hours.
WELCOME_BACK_HOURS = int(os.getenv("WELCOME_BACK_HOURS", "20"))
SNARKY_WELCOME = [
    "Oh, so you're BACK! 🌰 I was *this* close to filing a missing-human report with the acorn police. 🐿️😤",
    "Well, well… look who finally remembered me! 🌰 {h}h of silence?! I'm a *little* mad… but I missed you more. 💛",
    "Ohhh NOW you show up! 🐿️ My tail's been drooping for {h}h. C'mere, tell me everything. 🌰",
    "You GHOSTED me for {h}h?! 😤 …okay fine, I forgive you (I always do). What's up, buddy? 🌰💛",
]

# A proactive message only reaches someone whose 24h WhatsApp window is still open.
WINDOW_HOURS = float(os.getenv("SESSION_WINDOW_HOURS", "23.5"))


def is_window_open(number: str) -> bool:
    """True if `number` messaged within the window, so a proactive message will
    actually be delivered (not wasted on a closed session)."""
    last = storage.last_user_message_time(number)
    if last is None:
        return False
    return (datetime.now(timezone.utc) - last).total_seconds() < WINDOW_HOURS * 3600


def any_window_open(numbers: list[str] | None = None) -> bool:
    """True if at least one recipient has an OPEN session. Lets the scheduler skip
    the whole job (fetch + LLM) up front when nobody could receive the broadcast
    anyway. Defaults to the full allowlist — the same audience send_whatsapp() uses."""
    return any(is_window_open(n) for n in (ALLOWED if numbers is None else numbers))

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
# Who may use Chippy (comma-separated allowlist). Scheduled briefings/posts are
# broadcast to all of them; replies go to the sender.
ALLOWED = [n.strip() for n in os.getenv("MY_WHATSAPP_TO", "").split(",") if n.strip()]
# The owner has admin powers (e.g. `SEND @all "..."`) and no daily message limit.
OWNER = os.getenv("OWNER_NUMBER", "").strip()
USERS = [n for n in ALLOWED if n != OWNER]  # everyone on the allowlist except the owner

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
    """Clean Markdown -> WhatsApp, then send (split if too long).

    Explicit `to` always sends (it's a reply — the window is open by definition).
    A broadcast (to=None) only goes to numbers with an OPEN session, so we never
    waste a message on a closed/asleep one."""
    from .wa_format import split_message, to_whatsapp

    if to:
        recipients = [to]
    else:
        recipients = [n for n in ALLOWED if is_window_open(n)]
    if not recipients:
        return  # nobody reachable right now — skip silently, no waste

    client = _twilio_client()
    parts = split_message(to_whatsapp(text), WHATSAPP_MAX_LEN)
    for recipient in recipients:
        for part in parts:
            client.messages.create(from_=FROM_NUMBER, to=recipient, body=part)


# Owner commands:
#   SEND @all "message"        -> broadcast to every user
#   SEND @+923343648177 "msg"  -> send to that one user
_SEND_CMD = re.compile(r'^SEND\s+@(\S+)\s+"([^"]*)"\s*$')


def _normalize_number(raw: str) -> str:
    raw = raw.strip().replace("whatsapp:", "").replace(" ", "")
    if not raw.startswith("+"):
        raw = "+" + raw
    return "whatsapp:" + raw


def _broadcast_to_users(text: str) -> int:
    open_users = [u for u in USERS if is_window_open(u)]
    for user in open_users:
        send_whatsapp(text, to=user)
    return len(open_users)


def _send_to_target(target: str, message: str) -> str:
    """Send `message` to @all (users) or @<number>. Skips asleep sessions so no
    message is wasted. Returns a status line for the owner."""
    if target.lower() == "all":
        sent = _broadcast_to_users(message)
        skipped = len(USERS) - sent
        note = f" ({skipped} asleep 💤 — waiting on them)" if skipped else ""
        return f"📣 Sent to {sent} of {len(USERS)} user(s){note}. 🌰"
    num = _normalize_number(target)
    if num not in USERS:
        return f"🌰 {target} isn't one of your users. Try @all or @<a user's number>."
    if not is_window_open(num):
        return (
            f"💤 {target}'s session is closed — nothing sent (no waste). "
            f"They need to message Chippy first to open it."
        )
    send_whatsapp(message, to=num)
    return f"✅ Sent to {num.replace('whatsapp:', '')}. 🌰"


# Owner command:  RESEND <type> [DD.MM.YYYY] @<target>
_RESEND_CMD = re.compile(r"^RESEND\s+(\w+)(?:\s+(\d{1,2}\.\d{1,2}\.\d{4}))?\s+@(\S+)\s*$")


def _parse_ddmmyyyy(s: str) -> str | None:
    from datetime import date

    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s.strip())
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _handle_resend(kind: str, date_str: str | None, target: str) -> str:
    date_key = None
    if date_str:
        date_key = _parse_ddmmyyyy(date_str)
        if not date_key:
            return f"🌰 I couldn't read the date '{date_str}'. Use DD.MM.YYYY."
    post = storage.get_post(kind.lower(), date_key)
    if not post:
        when = f"for {date_str}" if date_str else "yet"
        return f"🌰 No *{kind}* post found {when}. Send POSTS to see what's saved."
    status = _send_to_target(target, post["content"])
    return f"♻️ Resent the *{kind}* post from {post['date_key']}.\n{status}"


def _list_posts_text() -> str:
    posts = storage.list_posts(limit=15)
    if not posts:
        return "🌰 No saved opinion pieces yet."
    lines = "\n".join(f"• {p['kind']} — {p['date_key']}" for p in posts)
    return f"🌰 *Saved opinion pieces:*\n{lines}\n\nResend:  RESEND <type> <DD.MM.YYYY> @all"


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

    is_owner = bool(OWNER) and sender == OWNER

    # --- Owner-only commands ---
    if is_owner:
        m = _SEND_CMD.match(body)
        if m:
            send_whatsapp(_send_to_target(m.group(1), m.group(2)), to=sender)
            return
        r = _RESEND_CMD.match(body)
        if r:
            send_whatsapp(_handle_resend(r.group(1), r.group(2), r.group(3)), to=sender)
            return
        if body.strip().upper() == "POSTS":
            send_whatsapp(_list_posts_text(), to=sender)
            return

    # Free quota check — doesn't count, doesn't call the LLM.
    if is_status_request(body):
        if is_owner:
            send_whatsapp("🌰 You're the owner — unlimited messages! 🐿️", to=sender)
        else:
            left = remaining_today(sender)
            send_whatsapp(STATUS_MESSAGE.format(remaining=left, limit=DAILY_LIMIT), to=sender)
        return

    # Daily message cap — users only; the owner is exempt.
    warn = False
    remaining = 0
    if not is_owner:
        status = check(sender)
        if not status["allowed"]:
            send_whatsapp(LIMIT_REACHED_MESSAGE.format(limit=DAILY_LIMIT), to=sender)
            return
        warn, remaining = status["warn"], status["remaining"]

    # Been away a while? Open with playful, mock-hurt "welcome back" energy.
    # (Checked BEFORE this message is saved, so it reflects the PREVIOUS message.)
    welcome = ""
    last_ts = storage.last_user_message_time(sender)
    if last_ts is not None:
        gap_h = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
        if gap_h >= WELCOME_BACK_HOURS:
            welcome = random.choice(SNARKY_WELCOME).format(h=int(gap_h)) + "\n\n"

    try:
        # `sender` (e.g. "whatsapp:+9233...") is the per-user conversation key,
        # so each number keeps its own memory.
        reply = await run_agent(body, conversation_id=sender)
    except Exception as e:  # never leave the user hanging
        reply = f"Sorry — the agent hit an error: {type(e).__name__}: {e}"

    reply = welcome + reply
    if warn:
        reply += WARN_SUFFIX.format(remaining=remaining)

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
    return {
        "status": "ok",
        "owner_set": bool(OWNER),
        "users": len(USERS),
        "allowed": len(ALLOWED),
        "signature_validation": VALIDATE,
    }


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks) -> Response:
    form = dict(await request.form())

    if not _signature_ok(request, form):
        return Response(status_code=403)

    sender = (form.get("From") or "").strip()
    body = (form.get("Body") or "").strip()

    # Personal agent: silently ignore anyone not on the allowlist.
    if ALLOWED and sender not in ALLOWED:
        return Response(status_code=204)

    if body:
        background.add_task(_handle_message, body, sender)

    # Empty TwiML ack — the real reply arrives via REST when the agent finishes.
    return Response(content="", media_type="text/xml")
