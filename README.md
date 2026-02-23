# OpenClaw Telegram Bot

An AI Telegram bot powered by **OpenClaw** (agent framework) + **OpenCode CLI** (free LLM access) running on an AWS VPS. Completely free — no paid API keys required.

The bot (**Claw** 🦞) can answer questions, search the web, fetch live news (including Estonian news), and maintain memory across conversations.

---

## Architecture

```
Telegram ──► OpenClaw Gateway ──► CLI Router v5 ──► OpenCode CLI ──► Free LLM
                (:18789)              (:4097)          (subprocess)   (MiniMax/GLM-5)
```

**CLI Router v5** (`cli_router.py`) is the core of this project. It:
1. Receives OpenClaw's ~48KB requests (system prompt + history + 22 tool schemas)
2. Detects user intent (news, web search, URL fetch)
3. Pre-executes web tools (DuckDuckGo search, page fetch) before calling the LLM
4. Compresses context from 48KB to ~4KB
5. Calls `opencode run` as a subprocess
6. Returns the response as a proper SSE stream

This pre-execution approach is what makes the bot actually useful — free-tier LLMs describe tools but don't call them reliably. The router handles tool execution and lets the LLM just synthesize the results.

---

## Features

- **Web search**: DuckDuckGo search via `ddgs` library
- **Live news**: Estonian news fetched from ERR/Postimees on request
- **Page fetching**: Stealth Playwright-based content extraction
- **Memory**: MEMORY.md for long-term context across sessions
- **Task list**: TODOS.md the agent reads and updates
- **Heartbeat**: Hourly self-check (disk, services, tasks)
- **Cron jobs**: Morning briefing, system check, news summary
- **Free tier**: No API keys needed — OpenCode's Antigravity auth provides LLM access

---

## Quick Start

See [SETUP.md](SETUP.md) for the full step-by-step guide.

Short version:

```bash
# 1. Install OpenCode
curl -fsSL https://opencode.ai/install | bash
~/.opencode/bin/opencode auth  # GitHub OAuth

# 2. Install OpenClaw
npm install -g openclaw
npx openclaw setup

# 3. Deploy router
scp cli_router.py ubuntu@<VPS-IP>:/home/ubuntu/cli_router.py

# 4. Configure OpenClaw to use router
# Edit ~/.openclaw/openclaw.json (see SETUP.md for full config)

# 5. Start services
systemctl --user start openclaw-router openclaw-gateway
```

---

## Files

| File | Purpose |
|------|---------|
| `cli_router.py` | The router — deploy this to VPS |
| `SETUP.md` | Full setup guide from scratch |
| `HANDOVER.md` | Current architecture, configuration, operations |
| `CLI_ROUTER.md` | Router v5 technical reference |
| `PROJECT_HANDBOOK.md` | Quick-reference ops sheet |
| `TAILSCALE_SETUP.md` | Network/VPN notes |
| `VPS_SETUP_JOURNAL.md` | Chronological build history and lessons learned |

---

## Requirements

- AWS EC2 (t3.micro, Ubuntu 22.04+)
- Node.js 20+
- Python 3.10+
- Tailscale (for stable SSH access)
- OpenCode CLI (for free LLM access via Antigravity auth)
- OpenClaw (agent framework)
- Playwright + ddgs (for web tools)

---

## Models

Uses OpenCode's free Antigravity tier (no API key needed, GitHub auth):

| Model | Notes |
|-------|-------|
| `opencode/minimax-m2.5-free` | Default — 1M context, good synthesis |
| `opencode/glm-5-free` | Better instruction-following |
| `opencode/trinity-large-preview-free` | Experimental |

---

## Lessons Learned

The full story is in [VPS_SETUP_JOURNAL.md](VPS_SETUP_JOURNAL.md). Key lessons:

- **Never set Tailscale exit-node on a remote server** — if the exit node goes offline, the VPS is unreachable with no self-recovery
- **OpenClaw always streams** — SSE is mandatory, plain JSON is silently discarded
- **Pre-execute tools in the router** — don't rely on free LLMs to call tools correctly
- **Check what's actually on port 4097** — an old wrapper was blocking the new router undetected
