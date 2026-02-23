# VPS Setup Journal

Chronological log of what was built and what broke. For current state, see [HANDOVER.md](HANDOVER.md).

---

## 2026-02-15: Initial Setup

- Launched AWS EC2 t3.micro in ap-southeast-2 (Sydney)
- Installed Node.js 20, OpenClaw, Tailscale
- Created Telegram bot `@assistant_clauze_bot` via BotFather
- Configured NVIDIA API (Kimi K2.5) as model provider — worked but slow (~10–20s)
- Basic bot responding in Telegram

---

## 2026-02-17: Router v1 + Disk Crisis

- Built CLI Router v1 to wrap OpenCode CLI for faster free-tier model access
- **Crisis**: VPS disk hit 100% — 4,028 leaked `.fbd*.so` files in `/tmp` consuming 16.5GB
  - OpenClaw silently returned empty `content: []` responses
  - Deleted files: `find /tmp -name '*.fbd*.so' -delete`
  - Added hourly cron to clean these: `0 * * * * find /tmp -name '*.fbd*.so' -mmin +60 -delete`
- **Bug found**: Router v1 only returned plain JSON — OpenClaw requires SSE streaming (`stream: true` always, OpenAI JS SDK behaviour)
- Fixed: added `text/event-stream` SSE response format (Router v2)

---

## 2026-02-18: Web Browser Skill + Context Problem

- Deployed Playwright-based web browser skill
  - `web_search.py` — DuckDuckGo via `ddgs` Python library (search engines block headless browsers directly)
  - `web_fetch.py` — Stealth Playwright page reader
  - `web_browse.py` — Persistent browser profiles for authenticated sites
- Added stealth anti-detection JS injection for page fetching
- **MAIN BUG FOUND**: Router was stripping all context from OpenClaw requests
  - OpenClaw sends ~48KB (system prompt with identity, AGENTS.md, 22 tool JSON schemas, conversation history)
  - Router was only forwarding the last user message text
  - Bot had no memory, no identity, couldn't use skills
- Built Router v3: `build_mega_prompt()` packs everything into one prompt for opencode CLI

---

## 2026-02-18: kimi-k2.5-free Removed

- OpenCode dropped `kimi-k2.5-free` from the free tier without notice
- Switched primary model to `opencode/glm-5-free`
- Added router auto-remap: any model name containing "kimi" → glm-5-free
- Available free models: `glm-5-free`, `minimax-m2.5-free`, `trinity-large-preview-free`

---

## 2026-02-19: Tailscale Exit Node Disaster

- Attempted to set Tailscale exit node on VPS for better web browsing IPs
  - `tailscale set --exit-node=100.70.48.72` (Android TV stick)
- Android TV stick went offline → all VPS routing immediately broken
- SSH unreachable, public IP unreachable — setting persists across reboots
- **Recovery**: AWS EC2 console → Instance → Edit User Data →
  ```bash
  #!/bin/bash
  tailscale set --exit-node=
  ```
  Stop instance → Start instance (not reboot — user data runs on start)
- VPS routing restored; re-added ed25519 SSH key via EC2 Instance Connect

**Lesson**: Never set exit-node on a remote server unless you have out-of-band rescue access.

---

## 2026-02-20: Full Deployment

- VPS back online after Tailscale fix
- Re-added SSH authorized key (ed25519 from dev machine)
- Deployed Router v3 to VPS
- Updated OpenClaw config: model `opencode/glm-5-free`, exec security=full, ask=off
- Restarted router and gateway — both confirmed running
- Gateway log: `agent model: opencode-local/opencode/glm-5-free`
- Bot responding in Telegram with full context and memory

---

## 2026-02-22: Personal Agent Features

Researched OpenClaw community patterns. Deployed:

- **Heartbeat** (every 60 min, 07:00–23:00): System monitoring checklist in `HEARTBEAT.md`
  - Checks disk usage, router/gateway ports, RAM
  - Reviews TODOS.md for reminders
- **MEMORY.md**: Long-term memory file — user info, key projects, preferences
- **TODOS.md**: Task list the agent can read and update
- **3 cron jobs**: Morning Briefing (daily 08:00), System Check (every 6h), Estonian News (every 12h)
- Router v4: Aggressive prompt compression (48K → 8K chars), switched to `minimax-m2.5-free` for speed
- Increased router timeout from 90s to 300s (user: "change timeouts so bot waits for answer not spits out apologies")

Test results: simple queries 5s, todo management 10s, system status 25s, memory recall 44s.

---

## 2026-02-23: Router v5 + Critical Bug Fix

**Problem**: Bot stopped answering — just listed its capabilities repeatedly for every query.

**Root cause investigation** (log analysis):
```
prompt=12000  # hitting the 12K char max limit
```
With 246+ messages in the conversation, the Router v4 history loop never correctly accumulated total length:
```python
# BROKEN — history_text never updated, so all 246 messages were added:
history_text = ''
for h in reversed(recent):
    candidate = h + '\n' + history_text   # always comparing single entry vs 4000 limit
    if len(candidate) > MAX_HISTORY_CHARS:
        break  # never triggered on individual entries
    kept.insert(0, h)
```
All 246 history entries → filled 12K char limit → final truncation cut off user message → model saw system + history but **no question** → defaulted to describing itself.

**Second problem found**: Router returns plain text (`delta.content`) not tool calls (`tool_calls` JSON). Free-tier LLMs say "I can search the web" but can't actually call tools through the `opencode run` single-shot interface.

**Router v5 fixes**:
1. History loop correctly tracks `total_len` — history capped at 2,500 chars
2. User message always protected from truncation (truncate from beginning, not end)
3. **Tool pre-execution layer**: router detects intent (estonian_news, web_search, web_fetch), runs `web_search.py` / `web_fetch.py` on VPS _before_ calling LLM, injects real results into prompt
4. LLM now just synthesizes pre-fetched data — no tool calling required

**Test results** (2026-02-23):
- "Tell me Estonian news for today" → real headlines (Henry Sildaru Olympic silver, etc.) in 37s
- "7 * 8" → "56" in 4s
- "search for latest AI models 2026" → real search results in 36s

Both services converted to systemd user services for auto-restart on failure.

---

## Lessons Learned

1. **Never set Tailscale exit-node on a remote server** — if exit node goes offline, VPS becomes completely unreachable with no self-recovery
2. **OpenClaw always streams** — `stream: true` is hardcoded in OpenAI JS SDK; any provider must return `text/event-stream`
3. **OpenCode CLI is stateless** — each `opencode run` is fresh; all context must be packed into every call
4. **Free LLMs describe tools, they don't call them** — pre-execute tools in the router instead of relying on model function-calling
5. **Context budget matters** — with 246-message history, naive packing fills 12K chars before user message is added
6. **Test with `stream: false` first** — easier to debug than streaming JSON chunks
7. **Search engines block headless browsers** — use `ddgs` Python library for search, not browser-based scraping
8. **Always check what's actually on port 4097** — an old `opencode_wrapper.py` was squatting the port, blocking the new router for days
9. **Log everything** — `/tmp/router_debug.log` was essential for diagnosing both the truncation bug and the old wrapper issue
