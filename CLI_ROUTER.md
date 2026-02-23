# CLI Router v5 — Technical Reference

The router is the core of the system: a Python HTTP server that receives OpenClaw's OpenAI-compatible requests and proxies them to the OpenCode CLI, adding tool pre-execution along the way.

**File**: `cli_router.py`
**Port**: 4097 (loopback only)
**Service**: `openclaw-router.service` (systemd user service)

---

## Why it exists

OpenClaw sends ~48KB per request: system prompt (SOUL.md, AGENTS.md, 22 tool JSON schemas) + full conversation history + current user message. OpenCode CLI is stateless — each `opencode run` is a fresh subprocess. The router bridges this gap.

Without the router, either:
- Context is lost every message (no memory, identity, or skills)
- The full 48KB is sent to the LLM and overwhelms the free-tier context window

---

## Architecture

```
POST /v1/chat/completions   (from OpenClaw, stream=true always)
          │
          ├─ Parse messages array (system + history + user)
          ├─ Clean metadata wrappers from user messages
          ├─ INTENT DETECTION → pre-execute tools
          │     estonian_news → web_search.py (ERR/Postimees sites)
          │     web_search    → web_search.py (DuckDuckGo)
          │     web_fetch     → web_fetch.py (page content)
          ├─ Compress system prompt (48KB → ~2KB)
          ├─ Build compact prompt:
          │     [system] + [history, max 2500 chars] + [tool results] + [USER: ...]
          ├─ subprocess: opencode run -m <model> "<prompt>"
          └─ Format response as SSE text/event-stream → return to OpenClaw
```

---

## Key functions

### `detect_intent(user_msg)` → `(intent, param)`

Examines the user message for keywords:

| Intent | Trigger | Param |
|--------|---------|-------|
| `estonian_news` | "estonia"/"eesti" + "news"/"uudised"/"today"/"tell" | raw message |
| `web_search` | "search"/"look up"/"find"/"google"/"research" | extracted query |
| `web_fetch` | URL in message (https://...) | the URL |
| `None` | anything else | raw message |

### `pre_execute_tools(user_msg)` → `str or None`

Calls the appropriate tool and returns formatted results to inject into the prompt.

- **Estonian news**: runs `web_search.py` with `site:err.ee OR site:postimees.ee OR site:delfi.ee`, falls back to general search
- **Web search**: runs `web_search.py` with the detected query
- **Web fetch**: runs `web_fetch.py` on the URL

Results are prefixed `LIVE WEB DATA:` or `LIVE WEB SEARCH RESULTS:` so the LLM knows they're real data.

### `compress_system_prompt(text)` → `str`

Reduces OpenClaw's ~26KB system prompt to ~2KB by extracting:
1. IDENTITY.md content (agent name/persona)
2. USER.md content (who the user is)
3. Behavior/personality rules
4. A hardcoded action mandate prefix

The prefix is always:
```
"You are Claw 🦞, an AI assistant running on a VPS.
User: DaN (@Iselter).
Be direct, concise, opinionated. Do the task, don't describe what you could do.
When given web search results or tool output, synthesize them into a useful answer."
```

### `build_prompt(messages, tools)` → `str`

Assembles the final prompt:
1. Compressed system (~2K chars)
2. Recent history — **correctly** limited to 2,500 chars (v4 bug: `history_text` never updated so all 246+ messages were included, filling the limit and cutting off the user message)
3. Tool results (pre-exec data, up to 3K chars)
4. `USER: <current message>` — always present, never truncated
5. `Respond:`

If total exceeds 10K chars, truncates from the **beginning** (old history), never from the end where the user message is.

---

## SSE Streaming

OpenClaw uses the OpenAI JS SDK which always sends `stream: true`. The router returns a proper SSE response:

```
data: {"choices":[{"delta":{"role":"assistant","content":""},...}]}

data: {"choices":[{"delta":{"content":"<full response text>"},...}]}

data: {"choices":[{"delta":{},"finish_reason":"stop"}],...}

data: [DONE]
```

The full response is sent in one content chunk (not token-by-token), which works fine with OpenClaw's `streamMode: "partial"` setting.

---

## Configuration

Via environment variables (set in systemd service):

| Variable | Default | Description |
|----------|---------|-------------|
| `ROUTER_MODEL` | `opencode/minimax-m2.5-free` | LLM model to use |
| `OPENCODE_BIN` | `/home/ubuntu/.opencode/bin/opencode` | OpenCode binary path |
| `ROUTER_TIMEOUT` | `300` | Max seconds to wait for LLM response |
| `ROUTER_PORT` | `4097` | HTTP server port |

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/models` | Returns list of available models |
| `POST` | `/v1/chat/completions` | Main completions endpoint |
| `GET` | `/` | Status check (`{"status": "openclaw router v5"}`) |

---

## Prompt size limits (v5)

| Section | Limit |
|---------|-------|
| `MAX_SYSTEM_CHARS` | 2,000 |
| `MAX_HISTORY_CHARS` | 2,500 |
| `MAX_TOOL_RESULT_CHARS` | 3,000 |
| `MAX_PROMPT_CHARS` | 10,000 |
| User message | Always 100% included |

---

## Debug log

All activity is logged to `/tmp/router_debug.log`:

```
[08:40:51] Intent detected: estonian_news
[08:40:51] Pre-exec: fetching Estonian news
[08:40:54] Prompt built: 1434 chars, tool_context: True, history_entries: 0
[08:41:28] LLM response (1375 chars): ## Estonian News for Today...
[08:41:28] HTTP: "POST /v1/chat/completions HTTP/1.1" 200 -
```

---

## Model remapping

The router auto-remaps model names that have been removed from OpenCode's free tier:
- Any model containing `kimi` → `opencode/glm-5-free`

---

## Deploy

From local machine:
```bash
scp cli_router.py ubuntu@100.93.10.110:/home/ubuntu/cli_router.py
ssh ubuntu@100.93.10.110 "systemctl --user restart openclaw-router"
```

---

## Test directly on VPS

```bash
# Simple query (no tool pre-exec, fastest path)
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"what is 9 * 9"}]}'

# Estonian news (triggers estonian_news intent → web_search.py)
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"Tell me Estonian news for today"}]}'

# Web search intent
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"search for best AI tools 2026"}]}'
```

---

## Version history

| Version | Date | Key changes |
|---------|------|-------------|
| v1 | 2026-02-17 | Basic proxy, stripped context (only last user message forwarded) |
| v2 | 2026-02-17 | Added SSE streaming (plain JSON was silently discarded by OpenClaw) |
| v3 | 2026-02-18 | Full context passing: `build_mega_prompt()` with system + history + user |
| v4 | 2026-02-22 | Prompt compression (48K→8K), switched to minimax-m2.5-free, 300s timeout |
| v5 | 2026-02-23 | **Fixed history loop bug** (user msg was being truncated off), tool pre-execution, intent detection |
