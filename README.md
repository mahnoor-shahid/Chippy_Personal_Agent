# Personal Agent

A modular **MCP server** of personal-automation tools, plus a small **agent** that
drives those tools from WhatsApp and on a schedule.

## The big idea

The MCP server is the reusable core. It is consumed by two independent front-ends:

```
                     ┌──────────────────────────┐
                     │   MCP Server (modular)    │
                     │   - get_ai_news()         │
                     │   - (later) draft_post()  │
                     └────────────┬──────────────┘
                                  │  MCP protocol
              ┌───────────────────┴────────────────────┐
              │                                         │
   ┌──────────▼───────────┐               ┌─────────────▼────────────┐
   │   agent/  (our app)  │               │   ChatGPT (Apps SDK)     │
   │   LLM brain          │               │   manual use, optional   │
   │   + Twilio WhatsApp  │               │   (for learning the SDK) │
   │   + 7am scheduler    │               └──────────────────────────┘
   └──────────────────────┘
```

> **Why two front-ends?** ChatGPT's Apps SDK lets your tools appear *inside the
> ChatGPT app for manual use* — it can't be triggered by WhatsApp or run on a 7am
> cron. So automation runs on our own `agent/`, which reuses the exact same MCP
> server. You still learn the Apps SDK by connecting the same server to ChatGPT.

## Layout

```
src/
  mcp_server/
    server.py          # FastMCP app; registers all tools
    config.py          # settings from env
    tools/
      ai_news.py       # get_ai_news tool  (register pattern)
    sources/
      rss.py           # raw news fetching (no LLM here)
  agent/               # (next) brain + Twilio webhook + scheduler
```

Each tool module exposes `register(mcp)` so adding a feature = drop a file in
`tools/` and add one import line. That's the modularity.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (use: source .venv/bin/activate on *nix)
pip install -r requirements.txt
cp .env.example .env            # then edit .env
```

Set `LLM_PROVIDER` (`openrouter` | `anthropic` | `openai` | `ollama`) and paste
its API key in `.env`. **A valid key is required** for the cloud providers; only
`ollama` (local open-source models) needs no key.

## Run the agent

```powershell
python -m src.agent "What's new in AI in the last 24 hours?"
python -m src.agent            # default morning-digest prompt
```

## WhatsApp (Twilio sandbox)

1. In `.env` set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and
   `MY_WHATSAPP_TO=whatsapp:+<your number>` (the bot only answers this number).
2. Join the sandbox: from WhatsApp, send `join <your-sandbox-code>` to the
   Twilio sandbox number (Console → Messaging → Try it out → WhatsApp).
3. Start the webhook and expose it:
   ```powershell
   uvicorn src.agent.whatsapp:app --port 8000
   ngrok http 8000          # in a second terminal
   ```
4. In the sandbox settings, set **"When a message comes in"** to
   `https://<your-ngrok>.ngrok-free.app/whatsapp` (HTTP **POST**), and save.
5. Message your bot on WhatsApp. Set `TWILIO_VALIDATE=true` once it works.

## Daily digest scheduler

Pushes the morning digest to WhatsApp at `DIGEST_HOUR` (`TIMEZONE`).

```powershell
python -m src.agent.scheduler --dry-run   # generate + print once (no Twilio)
python -m src.agent.scheduler --now       # generate + send once
python -m src.agent.scheduler             # run forever on the schedule
```

## Deploying on a VPS

Two long-running processes (run under systemd / pm2 / supervisor):

```bash
uvicorn src.agent.whatsapp:app --host 0.0.0.0 --port 8000   # inbound WhatsApp
python -m src.agent.scheduler                                # 7am digest
```

Put the webhook behind HTTPS (Caddy / nginx + Let's Encrypt) and point the
Twilio webhook at `https://<your-domain>/whatsapp`. Then `TWILIO_VALIDATE=true`.

## Run / test the MCP server

```bash
pip install -r requirements.txt

# Inspect tools interactively in a browser (MCP Inspector):
mcp dev src/mcp_server/server.py

# Or run it as a stdio server:
python -m src.mcp_server.server
```

## Roadmap

- [x] MCP server skeleton + modular tool registration
- [x] `get_ai_news` tool (RSS-based, LLM-free)
- [x] `agent/brain.py` — provider-agnostic MCP client + tool loop (OpenRouter/Anthropic/OpenAI)
- [x] `agent/whatsapp.py` — Twilio inbound webhook + `send_whatsapp()`
- [x] `agent/scheduler.py` — daily digest push (cron via APScheduler)
- [x] Ollama provider — local open-source models, no API key
- [x] Conversation memory + DB (`storage.py`, SQLite → Postgres-ready)
- [x] Chippy persona (`agent/persona.py`) — playful **and caring** companion
- [x] `tools/ai_newsletter.py` — up to 3 AI newsletters (beehiiv), summarized
- [x] `tools/world_news.py` — global headlines (Deutsche Welle RSS)
- [x] `tools/psx.py` — Pakistan Stock Exchange snapshot (KSE-100 etc.)
- [x] Composed 8am morning briefing (AI + world + markets), Europe/Berlin
- [x] `tools/youtube.py` — latest video + transcript (any language)
- [x] Daily LinkedIn opinion posts (TLDR @13:00, Stockify @16:00, Europe/Berlin)
- [x] WhatsApp formatter (`wa_format.py`) — Markdown → clean WhatsApp + smart split
- [x] Per-user 30/day message cap + subscribe nudge (`limits.py`)
- [x] `tools/web_search.py` — DuckDuckGo web search (no key)
- [x] `tools/reminders.py` — per-user reminders / to-dos (DB)
- [x] `tools/memory_facts.py` — remember/recall durable facts (DB)
- [x] `tools/weather.py` — current weather + forecast (Open-Meteo, no key)
- [x] LinkedIn drafting — native Chippy skill (uses web_search/news for material)
- [ ] Switch WhatsApp from Twilio → Meta Cloud API (cost)
- [ ] Phase 2 (SaaS): auth + per-user accounts + OpenRouter provisioning keys
- [ ] (optional) connect same server to ChatGPT via Apps SDK
```
