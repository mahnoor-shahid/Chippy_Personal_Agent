<div align="center">

# 🐿️ Chippy

### *Your friendly next-door AI agent — living in your WhatsApp*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with MCP](https://img.shields.io/badge/Built%20with-MCP-7C3AED)](https://modelcontextprotocol.io/)
[![LLM via OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-4F46E5)](https://openrouter.ai/)
[![WhatsApp](https://img.shields.io/badge/Chat-WhatsApp-25D366?logo=whatsapp&logoColor=white)](https://www.twilio.com/whatsapp)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![status](https://img.shields.io/badge/status-live%20🌰-success)]()

*Chippy texts you the news, watches the markets, remembers your stuff,*
*sets your reminders, and even drafts your posts — all with a cheeky squirrel grin.* 🌰 

</div>

---

## 🌰 Meet Chippy

Chippy is a **playful, caring little squirrel** who also happens to be a genuinely
capable personal assistant. He's not a faceless bot — he checks in on you, gets
excited about the markets, cracks the odd acorn joke, and gets real work done.

He lives in your **WhatsApp**, so there's no app to open — you just text a friend.

> *"Buddy!! 🌰 Do you know what's going on in the world today?!"*

## ✨ What Chippy can do

| | Capability |
|---|---|
| 📰 | **Daily AI newsletters** — summarises the latest issues into highlights |
| 🌍 | **World news** — top global headlines (Deutsche Welle) |
| 📈 | **PSX market summary** — KSE-100, sectors, top gainers/losers, most active |
| 🔎 | **Web search** — anything current or factual (DuckDuckGo, no key) |
| 🌦️ | **Weather** — current + forecast for any city (Open-Meteo) |
| ⏰ | **Reminders & to-dos** — *"remind me to call the bank at 3pm"* |
| 🧠 | **Long-term memory** — remembers facts you tell him, and your whole chat |
| 🎬 | **Video opinions** — fetches a channel's newest video + transcript |
| ✍️ | **LinkedIn drafts** — writes ready-to-post opinion pieces in his voice |

### ⏰ And he runs on a schedule (so you don't have to ask)

- **08:00** — Morning briefing: 🌍 world news + 📈 PSX market summary
- **13:00** — ✍️ Chippy's Opinion Piece (from a news channel's latest video)
- **16:00** — ✍️ Chippy's Opinion Piece (from a markets channel's latest video)

## 🧠 How Chippy thinks

The heart is a **modular MCP server** — a reusable toolbox. The same toolbox can be
driven by Chippy's own brain (for WhatsApp + scheduling) *or* plugged into ChatGPT.

```
                       ┌─────────────────────────────┐
                       │   MCP Server (12 tools)      │
                       │   news · markets · weather   │
                       │   reminders · memory · video │
                       └──────────────┬──────────────┘
                                      │  MCP protocol
                 ┌────────────────────┴────────────────────┐
                 │                                          │
      ┌──────────▼───────────┐                ┌─────────────▼────────────┐
      │   Chippy's brain      │                │   ChatGPT (Apps SDK)     │
      │   LLM + persona       │                │   optional / manual      │
      │   + WhatsApp          │                └──────────────────────────┘
      │   + scheduler         │
      │   + memory (SQLite)   │
      └──────────────────────┘
```

**Adding a new skill = one file** in `tools/` + one line in `server.py`. That's the
whole point — Chippy grows by dropping in modules.

## 🛠️ Tech stack

- **Python 3.12** · **FastMCP** (Model Context Protocol)
- **OpenRouter** for LLMs — free Nemotron for chat, `gpt-oss-120b` for scheduled jobs
  (provider-agnostic: also OpenAI, Anthropic, or local **Ollama**)
- **FastAPI** webhook · **Twilio** WhatsApp · **APScheduler** cron
- **SQLAlchemy** + SQLite (→ Postgres-ready) for memory & reminders
- Deployed on a **VPS** with **systemd** + **Caddy** (auto-HTTPS)

## 🚀 Quickstart (local)

```bash
git clone https://github.com/<you>/chippy.git
cd chippy
python -m venv .venv
.venv\Scripts\activate          # Windows  ·  source .venv/bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env            # then fill in your keys
```

Set `LLM_PROVIDER` + its API key in `.env` (only `ollama` needs no key). Then:

```bash
# Chat with Chippy in your terminal
python -m src.agent "Hey Chippy! what's new in AI?"

# Preview the morning briefing (no WhatsApp needed)
python -m src.agent.scheduler --dry-run

# Inspect the MCP tools in a browser
mcp dev src/mcp_server/server.py
```

## 📱 WhatsApp + ⏰ Scheduler

```bash
# Inbound WhatsApp webhook
uvicorn src.agent.whatsapp:app --host 127.0.0.1 --port 8000

# Scheduled briefing + opinion posts
python -m src.agent.scheduler
```

Point your Twilio WhatsApp webhook at `https://<your-domain>/whatsapp`. In
production these run as **systemd services** behind **Caddy** for HTTPS. Per-user
**30 messages/day** limit is built in.

## 🗺️ Roadmap

- [x] MCP server + 12 modular tools
- [x] Provider-agnostic brain (OpenRouter / OpenAI / Anthropic / Ollama)
- [x] Chippy persona — playful, caring, market-obsessed 🌰
- [x] WhatsApp + scheduled briefing & opinion posts
- [x] Memory + reminders (SQLite → Postgres-ready)
- [x] Per-user daily message limits
- [x] Deployed always-on (systemd + Caddy)
- [ ] Multi-number allowlist
- [ ] Switch WhatsApp Twilio → Meta Cloud API (cost)
- [ ] Phase 2 (SaaS): accounts + per-user OpenRouter provisioning keys
- [ ] Telegram channel

---

<div align="center">

*Made with 🌰 and a lot of tail-wagging.*

**Chippy** — because everyone deserves a friendly agent next door.

</div>
