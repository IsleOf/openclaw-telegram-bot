# OpenClaw Telegram Bot — Project Handover

**Last Updated**: 2026-02-23
**Status**: WORKING — Router v5 live with real web search, Estonian news, tool pre-execution
**Bot**: `@assistant_clauze_bot` on Telegram
**VPS**: AWS EC2 ap-southeast-2 · Tailscale IP `100.93.10.110`

---

## What This Is

An AI Telegram bot called **Claw** 🦞, powered by:
- **OpenClaw** — agent platform that connects the bot to Telegram, manages identity/memory/tools
- **OpenCode CLI** — provides free-tier LLM access (GLM-5, MiniMax M2.5, etc.) via Antigravity auth
- **CLI Router v5** — custom Python HTTP proxy that bridges the two, adds tool pre-execution

The bot can answer questions, search the web, fetch live news (including Estonian news), and remember context across a conversation. All LLMs are free-tier.

---

## Architecture

```
Telegram User
      │
      ▼
Telegram API
      │
      ▼
OpenClaw Gateway  (:18789, VPS)
      │  OpenAI-compatible POST /v1/chat/completions
      │  Body: ~48KB — system prompt + full conversation + 22 tool schemas
      ▼
CLI Router v5  (:4097, VPS)         ← this is cli_router.py
      │
      ├─ 1. Parse & clean messages (strip OpenClaw metadata wrappers)
      ├─ 2. Detect intent (estonian_news / web_search / web_fetch)
      ├─ 3. Pre-execute tools if needed
      │     └─ web_search.py → DuckDuckGo results
      │     └─ web_fetch.py  → page content
      ├─ 4. Compress OpenClaw's 26K system prompt → ~2K essential identity/rules
      ├─ 5. Build compact prompt (system + recent history + tool results + user msg)
      └─ 6. subprocess: opencode run -m minimax-m2.5-free "<prompt>"
      │
      ▼
OpenCode CLI → Free LLM (MiniMax M2.5 / GLM-5 via Antigravity auth)
      │
      ▼
Response text → formatted as SSE stream → OpenClaw → Telegram
```

### Why the router exists

OpenClaw sends ~48KB per request (full system prompt with all 22 tool JSON schemas, conversation history, user message). OpenCode CLI is stateless — `opencode run` is a single-shot subprocess. The router bridges the two by:
1. Compressing the 48KB down to ~3-5KB keeping only what matters
2. Pre-executing any tools the user needs (web search, news) so the LLM just synthesizes
3. Wrapping the response as a proper SSE stream (OpenClaw requires `stream: true` always)

---

## Services on VPS

| Service | Port | Managed by | Command |
|---------|------|-----------|---------|
| CLI Router v5 | 4097 | systemd user service `openclaw-router.service` | `systemctl --user restart openclaw-router` |
| OpenClaw Gateway | 18789 | systemd user service `openclaw-gateway.service` | `systemctl --user restart openclaw-gateway` |

Both services auto-restart on failure (`Restart=always`).

---

## Key Files

### On VPS (`/home/ubuntu/`)

| Path | Purpose |
|------|---------|
| `~/cli_router.py` | CLI Router v5 — the main proxy (deployed from local) |
| `~/.openclaw/openclaw.json` | OpenClaw config — model, Telegram, exec, heartbeat |
| `~/.config/systemd/user/openclaw-router.service` | Router systemd service |
| `~/.config/systemd/user/openclaw-gateway.service` | Gateway systemd service |
| `~/.openclaw/workspace/IDENTITY.md` | Agent name/emoji/persona |
| `~/.openclaw/workspace/USER.md` | Who the user is (DaN/@Iselter) |
| `~/.openclaw/workspace/SOUL.md` | Personality — direct, irreverent, resourceful |
| `~/.openclaw/workspace/AGENTS.md` | Full operational manual + web browsing instructions |
| `~/.openclaw/workspace/MEMORY.md` | Long-term memory store |
| `~/.openclaw/workspace/TODOS.md` | Task list the agent can read/update |
| `~/.openclaw/workspace/HEARTBEAT.md` | Periodic self-check instructions |
| `~/.openclaw/workspace/skills/web-browser/scripts/web_search.py` | DuckDuckGo search |
| `~/.openclaw/workspace/skills/web-browser/scripts/web_fetch.py` | Stealth page reader |
| `/tmp/router_debug.log` | Router log (rotates on restart) |

### Local (`/home/dev/openclaw controller/`)

| Path | Purpose |
|------|---------|
| `cli_router.py` | **Source of truth** for Router v5 — edit here, scp to VPS |
| `HANDOVER.md` | This file |
| `SETUP.md` | Full setup guide from scratch |
| `CLI_ROUTER.md` | Router v5 technical reference |
| `PROJECT_HANDBOOK.md` | Quick-reference ops sheet |
| `TAILSCALE_SETUP.md` | Network/VPN notes |
| `VPS_SETUP_JOURNAL.md` | Chronological setup history |

---

## OpenClaw Configuration (`~/.openclaw/openclaw.json`)

```json
{
  "models": {
    "providers": {
      "opencode-local": {
        "baseUrl": "http://127.0.0.1:4097/v1",
        "apiKey": "opencode-free",
        "api": "openai-completions",
        "models": [
          {"id": "opencode/minimax-m2.5-free", "name": "MiniMax M2.5 Free"},
          {"id": "opencode/glm-5-free",        "name": "GLM-5 Free"},
          {"id": "opencode/trinity-large-preview-free", "name": "Trinity Large Free"}
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {"primary": "opencode-local/opencode/minimax-m2.5-free"},
      "workspace": "/home/ubuntu/.openclaw/workspace"
    }
  },
  "tools": {
    "exec": {"host": "gateway", "security": "full", "ask": "off"}
  },
  "channels": {
    "telegram": {"enabled": true, "dmPolicy": "open", "streamMode": "partial"}
  },
  "heartbeat": {
    "every": "60m",
    "target": "last",
    "activeHours": {"start": "07:00", "end": "23:00"}
  }
}
```

---

## Router v5 — How It Works

### Intent Detection & Tool Pre-Execution

Before calling the LLM, the router inspects the user's message and runs tools on the VPS if needed:

| Detected intent | Trigger keywords | Action |
|----------------|-----------------|--------|
| `estonian_news` | estonia/eesti + news/uudised/today/tell | Runs `web_search.py` with ERR/Postimees/Delfi sites |
| `web_search` | search/look up/find/google/research | Runs `web_search.py` with extracted query |
| `web_fetch` | URL in message (https://...) | Runs `web_fetch.py` on that URL |
| *(none)* | anything else | No pre-exec, LLM answers from knowledge |

The tool results are injected into the prompt as `LIVE WEB DATA:` before the user message. The LLM synthesizes the pre-fetched data into a response. This is why the bot can actually fetch news — it doesn't rely on the LLM to call tools itself (free LLMs are unreliable at tool calling).

### The Critical v4 Bug That Was Fixed

In Router v4, the history accumulation loop had a bug:

```python
# BROKEN (v4): history_text never updated, all 246+ messages got added
history_text = ''
for h in reversed(recent):
    candidate = h + '\n' + history_text   # history_text is always ''
    if len(candidate) > MAX_HISTORY_CHARS:
        break  # never breaks on individual entries
    kept.insert(0, h)
```

With 246 conversation messages, ALL entries were added. This filled the 12K char limit entirely with history, **truncating the user's actual message off the end**. The model received: system + old history, but **no current question** → defaulted to listing its capabilities.

v5 fix: track `total_len` correctly, always protect user message from truncation.

### Prompt size budget (v5)

| Section | Limit |
|---------|-------|
| System prompt (compressed) | 2,000 chars |
| Conversation history | 2,500 chars |
| Tool results (pre-exec data) | 3,000 chars |
| Total max | 10,000 chars |
| User message | Always included (never truncated) |

---

## Response Times

| Query type | Typical time |
|-----------|-------------|
| Simple factual (math, definitions) | 4–8s |
| Web search / news (pre-exec + LLM synthesis) | 30–45s |
| System status check | 20–30s |
| Long conversation with history | 30–60s |

---

## Free Models Available (via OpenCode Antigravity auth)

| Model ID | Notes |
|----------|-------|
| `opencode/minimax-m2.5-free` | Current default. 1M context, good synthesis |
| `opencode/glm-5-free` | Better instruction-following, good fallback |
| `opencode/trinity-large-preview-free` | Experimental, minimal testing |

Models rotate without notice. The router exposes all three on `/v1/models` and auto-remaps `kimi` references (that model was removed from OpenCode free tier).

---

## Personal Agent Features

Deployed on 2026-02-22:

### Heartbeat (every 60 min, 07:00–23:00)
`HEARTBEAT.md` tells the agent to:
- Check disk usage (alert if >80%)
- Verify router and gateway are running
- Check RAM (alert if >85%)
- Review TODOS.md for reminders
- Log `HEARTBEAT_OK` if nothing needs attention

### Cron Jobs
| Job | Schedule | Purpose |
|-----|---------|---------|
| Morning Briefing | Daily 08:00 | Weather, news, task summary |
| System Check | Every 6h | Disk, memory, service health |
| Estonian News | Every 12h | Summarise ERR/Postimees headlines |

### Memory Files
- `MEMORY.md` — long-term user/project notes the agent reads on every session
- `TODOS.md` — task list the agent can add to and check off

---

## Operations

### SSH to VPS
```bash
ssh ubuntu@100.93.10.110
# Uses ed25519 key at ~/.ssh/id_ed25519
```

### Deploy updated router
```bash
scp "/home/dev/openclaw controller/cli_router.py" ubuntu@100.93.10.110:/home/ubuntu/cli_router.py
ssh ubuntu@100.93.10.110 "systemctl --user restart openclaw-router"
```

### Check status
```bash
# Both ports listening?
ss -tlnp | grep -E '4097|18789'

# Router activity (last 20 lines)
tail -20 /tmp/router_debug.log

# Gateway logs
ls /tmp/openclaw/ && tail -20 /tmp/openclaw/openclaw-*.log
```

### Test router directly
```bash
# Simple query (no tool pre-exec)
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"what is 9*9"}]}'

# Estonian news (triggers web_search pre-exec)
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"Tell me Estonian news for today"}]}'
```

### Restart everything
```bash
systemctl --user restart openclaw-router openclaw-gateway
systemctl --user status openclaw-router openclaw-gateway --no-pager
```

---

## Networking

| Item | Value |
|------|-------|
| VPS | AWS EC2 ap-southeast-2, instance `ip-172-31-36-81` |
| Public IP | 3.106.138.96 |
| Tailscale IP | 100.93.10.110 |
| SSH | `ssh ubuntu@100.93.10.110` (ed25519) |
| Router | `localhost:4097` (loopback only) |
| Gateway | `localhost:18789` (loopback only) |

**WARNING**: Never run `tailscale set --exit-node=...` on the VPS. If the exit node goes offline the VPS becomes completely unreachable (SSH breaks, persists through reboots). Recovery requires AWS EC2 console user-data script.

---

## Known Issues & Risks

| Risk | Mitigation |
|------|-----------|
| Free model rotation (OpenCode drops models without notice) | All 3 free models in config, auto-remap for old names |
| Long conversations fill context | History correctly capped at 2,500 chars in v5 |
| web_search.py impersonate warning | Cosmetic only — `"Impersonate 'chrome_X' does not exist, using 'random'"` — doesn't affect results |
| Tailscale exit node | See WARNING above |
| Disk filling with `.fbd*.so` files | Cron job cleans `/tmp` — check `df -h` if bot goes silent |

---

## Resolved Issues (History)

| Issue | What happened | Fix |
|-------|-------------|-----|
| SSH broken after reboot | ed25519 key not in authorized_keys | Added via EC2 Instance Connect |
| Old wrapper on port 4097 | `opencode_wrapper.py` running as systemd service was blocking Router v3 | Disabled `opencode-wrapper.service` |
| Bot very slow (60s) | 28K char mega-prompt overwhelming free-tier LLM | Router v4: compress to ~8K |
| Frequent "taking too long" messages | 90s timeout too short | Increased to 300s |
| Bot lists capabilities instead of acting | v4 history loop bug: user message cut off | Router v5: fixed loop, pre-execute tools |
| Tailscale exit node killed VPS | set --exit-node on VPS, Android TV went offline | EC2 user-data fix |
| Disk 100% full | 4,028 leaked `.fbd*.so` files (16.5GB) | Deleted files, added cleanup cron |
| `kimi-k2.5-free` removed | OpenCode dropped model | Router auto-remaps to glm-5-free |
| OpenClaw empty responses | Old wrapper returned plain JSON, not SSE | Router returns proper `text/event-stream` |
