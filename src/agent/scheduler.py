"""Scheduled jobs: the morning briefing + Chippy's daily LinkedIn opinion posts.

    python -m src.agent.scheduler              # run forever on schedule
    python -m src.agent.scheduler --now        # send the briefing once
    python -m src.agent.scheduler --dry-run    # print the briefing once (no Twilio)
    python -m src.agent.scheduler --linkedin tldr      # draft+print one post
    python -m src.agent.scheduler --linkedin stockify

Schedule (TIMEZONE): briefing at DIGEST_HOUR; LinkedIn posts at 13:00 and 16:00.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from functools import partial

from dotenv import load_dotenv

from .brain import ConfigError, run_agent

load_dotenv()

DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "8"))
TIMEZONE = os.getenv("TIMEZONE", "UTC")
# Scheduled jobs run unattended, so use a reliable model (not the free tier).
SCHEDULER_MODEL = os.getenv("SCHEDULER_MODEL", "openai/gpt-oss-120b")

# The 8am briefing is sent as TWO separate WhatsApp messages: Global, then PSX.
GLOBAL_PROMPT = (
    "Use get_world_news for the top global headlines. Then write a WhatsApp message "
    "BURSTING with excited, cheerful Chippy character — like a hyper little squirrel "
    "who can't WAIT to tell their best friend the news. 🌰\n"
    "- Open with a fun, high-energy hook, e.g. 'Buddy!! 🌰 Do you know what's going on "
    "out in the big wide world today?!'\n"
    "- Then 5-6 tight bullets of the top stories — facts stay clear, but sprinkle in "
    "your playful, cheerful voice and little reactions.\n"
    "- No link on any bullet. End with one line exactly: 'Source: Deutsche Welle'.\n"
    "Stay scannable, but make it exciting and full of personality. No AI news."
)

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

# Two opinion pieces per day, each from a channel's newest video.
LINKEDIN_JOBS = [
    {"key": "tldr", "name": "TLDR News", "channel": "https://www.youtube.com/@TLDRnews", "hour": 13},
    {"key": "stockify", "name": "Stockify", "channel": "https://www.youtube.com/@Stockifyyltd", "hour": 16},
]


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


def _stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


async def build_and_send(*, send: bool = True) -> None:
    """The 8am briefing: two separate messages — Global news, then PSX summary."""
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] building briefing (2 messages)...", flush=True)

    world = await run_agent(GLOBAL_PROMPT, model=SCHEDULER_MODEL)
    psx = await run_agent(PSX_PROMPT, model=SCHEDULER_MODEL)

    if send:
        from .whatsapp import send_whatsapp

        send_whatsapp(world)
        send_whatsapp(psx)
        print(f"[{stamp}] briefing sent (Global + PSX).", flush=True)
    else:
        _stdout_utf8()
        print("\n===== MESSAGE 1: 🌍 GLOBAL =====\n" + world, flush=True)
        print("\n===== MESSAGE 2: 📈 PSX =====\n" + psx, flush=True)


async def draft_linkedin(name: str, channel: str, *, send: bool = True) -> None:
    """Draft Chippy's opinion LinkedIn post from a channel's newest video."""
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] drafting LinkedIn post from {name}...", flush=True)
    text = await run_agent(_linkedin_prompt(name, channel), model=SCHEDULER_MODEL)

    if send:
        from .whatsapp import send_whatsapp

        send_whatsapp(text)
        print(f"[{stamp}] {name} LinkedIn draft sent.", flush=True)
    else:
        _stdout_utf8()
        print("\n" + text + "\n", flush=True)


async def _serve() -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        build_and_send,
        CronTrigger(hour=DIGEST_HOUR, minute=0, timezone=TIMEZONE),
        id="daily_briefing",
        misfire_grace_time=3600,
    )
    for job in LINKEDIN_JOBS:
        scheduler.add_job(
            partial(draft_linkedin, job["name"], job["channel"]),
            CronTrigger(hour=job["hour"], minute=0, timezone=TIMEZONE),
            id=f"linkedin_{job['key']}",
            misfire_grace_time=3600,
        )

    scheduler.start()
    times = ", ".join(f"{j['name']}@{j['hour']:02d}:00" for j in LINKEDIN_JOBS)
    print(
        f"Scheduler running ({TIMEZONE}) — briefing @ {DIGEST_HOUR:02d}:00; "
        f"LinkedIn: {times}. Ctrl+C to stop.",
        flush=True,
    )
    await asyncio.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chippy scheduler")
    parser.add_argument("--now", action="store_true", help="send the briefing once")
    parser.add_argument("--dry-run", action="store_true", help="print the briefing once")
    parser.add_argument(
        "--linkedin",
        choices=[j["key"] for j in LINKEDIN_JOBS],
        help="draft+print one LinkedIn post and exit",
    )
    args = parser.parse_args()

    try:
        if args.linkedin:
            job = next(j for j in LINKEDIN_JOBS if j["key"] == args.linkedin)
            asyncio.run(draft_linkedin(job["name"], job["channel"], send=False))
        elif args.dry_run:
            asyncio.run(build_and_send(send=False))
        elif args.now:
            asyncio.run(build_and_send(send=True))
        else:
            asyncio.run(_serve())
    except ConfigError as e:
        print(f"\nConfiguration error: {e}\n", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
