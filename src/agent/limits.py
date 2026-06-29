"""Per-user daily message limits + subscribe nudge.

Counts a user's sent messages since local midnight (TIMEZONE) and decides whether
to allow, warn, or block. Channel-agnostic so WhatsApp/Telegram both reuse it.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import storage

DAILY_LIMIT = int(os.getenv("DAILY_MESSAGE_LIMIT", "30"))
WARN_AT_REMAINING = int(os.getenv("WARN_AT_REMAINING", "6"))
TIMEZONE = os.getenv("TIMEZONE", "UTC")

LIMIT_REACHED_MESSAGE = (
    "🌰 Whew! You've nibbled through all {limit} of your daily messages — my little "
    "paws need a rest. 🐿️💤\n\n"
    "Want *unlimited* Chippy time? Reply *SUBSCRIBE* to upgrade — more nuts, more "
    "chats! ✨\n\nOtherwise I'll be back fresh tomorrow. 💛"
)

WARN_SUFFIX = (
    "\n\n🌰 _Psst — only {remaining} messages left today! Want more? "
    "Reply *SUBSCRIBE* to upgrade._"
)

# Free "how many left?" check — these words trigger a quota reply that does NOT
# count against the limit and never calls the LLM.
STATUS_KEYWORDS = {"status", "left", "quota", "remaining", "/status"}

STATUS_MESSAGE = (
    "🌰 You've got *{remaining}* of {limit} messages left today! "
    "Resets at midnight. 🐿️"
)


def _day_start_utc() -> datetime:
    try:
        tz = ZoneInfo(TIMEZONE)
    except Exception:
        tz = timezone.utc
    local_midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc)


def check(conversation_id: str) -> dict:
    """Decide what to do with an incoming message from `conversation_id`.

    Returns: {allowed, remaining, warn}. `remaining` is how many will be left
    AFTER this message is handled.
    """
    used = storage.count_user_messages_since(conversation_id, _day_start_utc())

    if used >= DAILY_LIMIT:
        return {"allowed": False, "remaining": 0, "warn": False}

    remaining = DAILY_LIMIT - (used + 1)
    return {"allowed": True, "remaining": remaining, "warn": remaining <= WARN_AT_REMAINING}


def remaining_today(conversation_id: str) -> int:
    """How many messages the user has left today (without consuming one)."""
    used = storage.count_user_messages_since(conversation_id, _day_start_utc())
    return max(0, DAILY_LIMIT - used)


def is_status_request(body: str) -> bool:
    return body.strip().lower() in STATUS_KEYWORDS
