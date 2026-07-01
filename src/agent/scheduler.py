"""Scheduled jobs: timed news briefings + PSX + Chippy's daily opinion posts.

    python -m src.agent.scheduler              # run forever on schedule
    python -m src.agent.scheduler --now        # send the news + PSX briefing once
    python -m src.agent.scheduler --dry-run    # print the news + PSX briefing (no Twilio)
    python -m src.agent.scheduler --linkedin tldr      # draft + print one opinion post
    python -m src.agent.scheduler --linkedin stockify

Schedule (TIMEZONE):
    07:00  🌍 World news (DW, morning)
    10:00  ✍️ Opinion piece (TLDR News)
    13:00  📈 PSX market summary
    14:00  📰 World news (The Economist)
    16:00  ✍️ Opinion piece (Stockify)
    18:00  🌍 World news (DW, evening)

Fail-safe: on ANY failure (fetch / extract / video / transcript / stale video /
drafting / bad output), Chippy messages ONLY the owner and sends nothing to users.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timezone
from functools import partial
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from .brain import ConfigError, run_agent

load_dotenv()

TIMEZONE = os.getenv("TIMEZONE", "UTC")
# Scheduled jobs run unattended, so use a reliable model (not the free tier).
SCHEDULER_MODEL = os.getenv("SCHEDULER_MODEL", "openai/gpt-oss-120b")
PSX_HOUR = int(os.getenv("PSX_HOUR", "13"))

DW_FEEDS = [
    f.strip()
    for f in os.getenv("WORLD_NEWS_FEEDS", "https://rss.dw.com/xml/rss-en-top").split(",")
    if f.strip()
]
ECONOMIST_FEEDS = [
    f.strip()
    for f in os.getenv(
        "ECONOMIST_FEEDS",
        "https://www.economist.com/latest/rss.xml,"
        "https://www.economist.com/international/rss.xml,"
        "https://www.economist.com/finance-and-economics/rss.xml",
    ).split(",")
    if f.strip()
]

# Timed news briefings — each fetches its own feeds at its own hour.
NEWS_JOBS = [
    {"key": "dw_am", "label": "🌍 World News (morning)", "source": "Deutsche Welle", "feeds": DW_FEEDS, "hour": 7},
    {"key": "economist", "label": "📰 The Economist", "source": "The Economist", "feeds": ECONOMIST_FEEDS, "hour": 14},
    {"key": "dw_pm", "label": "🌍 World News (evening)", "source": "Deutsche Welle", "feeds": DW_FEEDS, "hour": 18},
]

# Two opinion pieces per day, each from a channel's newest video.
LINKEDIN_JOBS = [
    {"key": "tldr", "name": "TLDR News", "channel": "https://www.youtube.com/@TLDRnews", "hour": 10},
    {"key": "stockify", "name": "Stockify", "channel": "https://www.youtube.com/@Stockifyyltd", "hour": 16},
]

# Cheesy "keep-alive" nudges — sent when a user's 24h WhatsApp window is about to
# close, to coax a reply (which keeps the window open for the daily posts).
KEEPALIVE_MESSAGES = [
    "🌰 Psst… it's been a while! I'm missing our little chats. How's your day going, buddy? 🐿️💛",
    "Hey you! 🌰 My tail's been twitching waiting to hear from you. Everything okay? Tell me something! 🐿️",
    "Knock knock! 🐿️ It's your favourite squirrel. Send me a quick hi so we don't drift apart? 🌰💛",
    "Buddy! 🌰 I've been stashing acorns AND juicy stories for you. Come say hi before I forget where I buried them! 🐿️",
]

PSX_PROMPT = (
    "Use get_psx_summary, then write a thorough but SUPER fun WhatsApp market summary "
    "— you LOVE the markets, so bring excited, cheerful, nutty Chippy energy! 🌰📈\n"
    "- Open with a high-energy hook, e.g. 'Buddy! Do you know what's going on in the "
    "market today?!'\n"
    "- *Indices*: KSE-100, KSE-30, All-Share with level and % change, plus how the key "
    "sector indices (Banking, Oil & Gas, etc.) moved.\n"
    "- *Top gainers* (3-4) and *Top losers* (3-4) with price and % change — react to "
    "them with personality!\n"
    "- *Most active* (3-4) by volume.\n"
    "- End with a playful squirrel-flavoured takeaway titled like '🌰 What my nutty "
    "eyes spotted:' giving the overall market vibe.\n"
    "Keep the numbers accurate and bullets clean, but make it cheerful and exciting. "
    "No links."
)


def _news_prompt(source: str, headlines: str) -> str:
    return (
        f"Here are today's top headlines from {source}:\n{headlines}\n\n"
        "Write a WhatsApp message BURSTING with excited, cheerful Chippy character — "
        "like a hyper little squirrel who can't WAIT to tell their best friend the news. 🌰\n"
        "- Open with a fun, high-energy hook, e.g. 'Buddy!! 🌰 Do you know what's going "
        "on in the world today?!'\n"
        "- Then 5-6 tight bullets of the MOST important stories — facts stay clear, but "
        "sprinkle in your playful, cheerful voice and little reactions.\n"
        f"- No link on any bullet. End with one line exactly: 'Source: {source}'.\n"
        "Stay scannable, but make it exciting and full of personality. No AI news."
    )


def _linkedin_prompt(name: str, channel: str) -> str:
    return (
        f"Use get_latest_video_transcript for the YouTube channel {channel} to learn "
        f"the topic. Then write Chippy's opinion as a ready-to-post LinkedIn post.\n"
        f"IMPORTANT: do NOT mention or reference the source channel or video, and do "
        f"NOT use the video's exact title — paraphrase the topic into a catchy, fun, "
        f"awesome hook of your own. Never say where the topic came from.\n"
        f"Format the reply as: first line exactly \"Hey! 🌰 It's time for Chippy's "
        f"Opinion Piece on <your catchy, fun paraphrased topic>!\", then a blank line, "
        f"then the LinkedIn post itself.\n"
        f"The post: PLAIN TEXT only (no markdown, no asterisks, no headings); a "
        f"scroll-stopping first line; 2-4 short, punchy paragraphs with a clear, "
        f"genuine point of view in Chippy's voice; 3-5 relevant hashtags on the last "
        f"line; under ~1200 characters."
    )


def _valid_linkedin(text: str):
    # A real post starts with the required opener; an "I can't do that" apology won't.
    if "Chippy's Opinion Piece" in text:
        return (True, "")
    return (False, "the draft didn't come out as a proper post (model couldn't use the material)")


def _stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _alert_owner(label: str, reason: str, send: bool) -> None:
    """On failure, message ONLY the owner — never broadcast broken content to users."""
    text = (
        f"⚠️ Chippy couldn't send the *{label}* today.\n\n"
        f"Reason: {reason}\n\n"
        f"I did NOT send anything to users. If you'd like to post something manually, "
        f'reply:  SEND @all "your message"'
    )
    if send:
        from .whatsapp import OWNER, send_whatsapp

        if OWNER:
            send_whatsapp(text, to=OWNER)
        else:
            _stdout_utf8()
            print("[OWNER ALERT — no OWNER_NUMBER set]\n" + text, flush=True)
    else:
        _stdout_utf8()
        print(f"\n[OWNER ALERT] {text}\n", flush=True)


async def _generate_or_alert(label, gen, send, validate=None):
    try:
        text = await gen()
    except Exception as e:
        _alert_owner(label, f"drafting error: {type(e).__name__}: {e}", send)
        return None
    if validate:
        ok, reason = validate(text)
        if not ok:
            _alert_owner(label, reason, send)
            return None
    return text


def _broadcast_or_print(label: str, text: str, send: bool) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    if send:
        from .whatsapp import send_whatsapp

        send_whatsapp(text)
        print(f"[{stamp}] {label}: sent to all users.", flush=True)
    else:
        _stdout_utf8()
        print(f"\n===== {label} =====\n{text}\n", flush=True)


async def send_news(label: str, source: str, feeds, *, send: bool) -> None:
    """Fetch a news source's headlines, format them, and broadcast — or alert the
    owner if the fetch/format fails."""
    from src.mcp_server.sources.rss import fetch_news

    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {label}: fetching {source}...", flush=True)
    try:
        items = await asyncio.to_thread(fetch_news, feeds, since_hours=48, max_items=12)
    except Exception as e:
        _alert_owner(label, f"couldn't fetch {source}: {type(e).__name__}: {e}", send)
        return
    if not items:
        _alert_owner(label, f"couldn't fetch any {source} headlines right now", send)
        return

    headlines = "\n".join(f"- {i.title}" for i in items)
    text = await _generate_or_alert(
        label, lambda: run_agent(_news_prompt(source, headlines), model=SCHEDULER_MODEL), send
    )
    if text is not None:
        _broadcast_or_print(label, text, send)


async def send_psx(*, send: bool) -> None:
    from src.mcp_server.tools.psx import fetch_psx_summary

    label = "📈 PSX market summary"
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {label}: fetching PSX...", flush=True)
    try:
        data = await asyncio.to_thread(fetch_psx_summary)
    except Exception as e:
        _alert_owner(label, f"couldn't fetch PSX: {type(e).__name__}: {e}", send)
        return
    if data.get("error") or not data.get("indices"):
        _alert_owner(label, data.get("error", "PSX returned no data"), send)
        return

    text = await _generate_or_alert(
        label, lambda: run_agent(PSX_PROMPT, model=SCHEDULER_MODEL), send
    )
    if text is not None:
        _broadcast_or_print(label, text, send)


async def draft_linkedin(name: str, channel: str, *, send: bool = True, key: str | None = None) -> None:
    """Draft + broadcast the opinion post. Alerts only the owner on any failure —
    including if the latest video is NOT new since the last post (no duplicates).
    On a real send, the post (prompt + text) is saved so the owner can RESEND it."""
    from . import storage
    from src.mcp_server.sources.youtube import latest_video_transcript

    label = f"✍️ {name} Opinion Piece"
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {label}: checking video...", flush=True)

    try:
        data = await asyncio.to_thread(latest_video_transcript, channel)
    except Exception as e:
        _alert_owner(label, f"couldn't fetch the video: {type(e).__name__}: {e}", send)
        return

    problem = data.get("error") or data.get("transcript_error")
    vid = data.get("video_id")
    title = data.get("title", "?")
    transcript = (data.get("transcript") or "").strip()

    if problem or not vid:
        _alert_owner(label, str(problem or "couldn't find the latest video")[:200], send)
        return
    if not transcript:
        _alert_owner(label, f"no transcript for the latest video ('{title}')", send)
        return

    # Only post if this is a NEW video (Stockify especially may not upload daily).
    vid_key = f"last_video:{channel}"
    last = await asyncio.to_thread(storage.kv_get, vid_key)
    if vid == last:
        _alert_owner(
            label,
            f"no NEW video since your last post — the latest is still '{title}'. "
            f"I didn't post a duplicate.",
            send,
        )
        return

    prompt = _linkedin_prompt(name, channel)
    text = await _generate_or_alert(
        label, lambda: run_agent(prompt, model=SCHEDULER_MODEL), send, validate=_valid_linkedin
    )
    if text is None:
        return

    _broadcast_or_print(label, text, send)
    if send:
        await asyncio.to_thread(storage.kv_set, vid_key, vid)  # remember we posted this video
        if key:  # store the opinion piece so the owner can RESEND it later
            date_key = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
            await asyncio.to_thread(storage.save_post, key, date_key, prompt, text)


async def run_briefing(*, send: bool) -> None:
    """News + PSX in one go — used by --now / --dry-run for a manual trigger."""
    await send_news("🌍 World News (morning)", "Deutsche Welle", DW_FEEDS, send=send)
    await send_psx(send=send)
    await send_news("📰 The Economist", "The Economist", ECONOMIST_FEEDS, send=send)


async def keepalive_check(*, send: bool = True) -> None:
    """Nudge any user whose 24h WhatsApp window is about to close, so a reply keeps
    it open. Sends at most one nudge per window (deduped via the KV store)."""
    from . import storage
    from .whatsapp import ALLOWED

    now = datetime.now(timezone.utc)
    for number in ALLOWED:
        last = await asyncio.to_thread(storage.last_user_message_time, number)
        if last is None:
            continue
        hours = (now - last).total_seconds() / 3600
        if not (22 <= hours < 24):  # only when the window is about to close
            continue
        key = f"nudge:{number}"
        stamp = last.isoformat()
        if await asyncio.to_thread(storage.kv_get, key) == stamp:
            continue  # already nudged for this window

        msg = random.choice(KEEPALIVE_MESSAGES)
        if send:
            from .whatsapp import send_whatsapp

            send_whatsapp(msg, to=number)
            print(f"[keepalive] nudged {number}", flush=True)
        else:
            _stdout_utf8()
            print(f"[keepalive -> {number}] {msg}", flush=True)
        await asyncio.to_thread(storage.kv_set, key, stamp)


async def _serve() -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    sch = AsyncIOScheduler(timezone=TIMEZONE)
    for j in NEWS_JOBS:
        sch.add_job(
            partial(send_news, j["label"], j["source"], j["feeds"], send=True),
            CronTrigger(hour=j["hour"], minute=0, timezone=TIMEZONE),
            id=f"news_{j['key']}",
            misfire_grace_time=3600,
        )
    sch.add_job(
        partial(send_psx, send=True),
        CronTrigger(hour=PSX_HOUR, minute=0, timezone=TIMEZONE),
        id="psx",
        misfire_grace_time=3600,
    )
    for j in LINKEDIN_JOBS:
        sch.add_job(
            partial(draft_linkedin, j["name"], j["channel"], send=True, key=j["key"]),
            CronTrigger(hour=j["hour"], minute=0, timezone=TIMEZONE),
            id=f"linkedin_{j['key']}",
            misfire_grace_time=3600,
        )
    # Keep-alive: check hourly whether anyone's 24h window is about to close.
    sch.add_job(
        partial(keepalive_check, send=True),
        IntervalTrigger(hours=1),
        id="keepalive",
    )

    sch.start()
    lines = [f"{j['hour']:02d}:00  {j['label']}" for j in NEWS_JOBS]
    lines.append(f"{PSX_HOUR:02d}:00  📈 PSX market summary")
    lines += [f"{j['hour']:02d}:00  ✍️ {j['name']} opinion" for j in LINKEDIN_JOBS]
    print(
        f"Scheduler running ({TIMEZONE}):\n  " + "\n  ".join(sorted(lines)) + "\nCtrl+C to stop.",
        flush=True,
    )
    await asyncio.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chippy scheduler")
    parser.add_argument("--now", action="store_true", help="send the news + PSX briefing once")
    parser.add_argument("--dry-run", action="store_true", help="print the news + PSX briefing once")
    parser.add_argument(
        "--linkedin",
        choices=[j["key"] for j in LINKEDIN_JOBS],
        help="draft + print one opinion post and exit",
    )
    parser.add_argument("--keepalive", action="store_true", help="run the keep-alive check once")
    args = parser.parse_args()

    try:
        if args.keepalive:
            asyncio.run(keepalive_check(send=False))
        elif args.linkedin:
            job = next(j for j in LINKEDIN_JOBS if j["key"] == args.linkedin)
            asyncio.run(draft_linkedin(job["name"], job["channel"], send=False))
        elif args.dry_run:
            asyncio.run(run_briefing(send=False))
        elif args.now:
            asyncio.run(run_briefing(send=True))
        else:
            asyncio.run(_serve())
    except ConfigError as e:
        print(f"\nConfiguration error: {e}\n", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
