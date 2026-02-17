# VPS Setup Journal - OpenClaw Telegram Bot

**Date**: 2026-02-17  
**Project**: OpenClaw Telegram Integration  
**Bot**: @assistant_clauze_bot

---

## Initial Problem

Telegram bot was not responding to messages. Investigation revealed:
1. Server disk was 100% full (29GB/29GB)
2. OpenClaw gateway couldn't function without disk space
3. Previous bot token may have been deprecated

---

## Fixes Applied

### 1. Disk Space Cleanup ✅
```bash
# Freed 7GB of space
rm -rf ~/.cache/*          # 5.5GB
npm cache clean --force    # npm cache
sudo journalctl --vacuum-time=3d  # old logs
find /tmp -name "openclaw*.log" -mtime +2 -delete  # old logs

# Result: 6.2GB free (79% usage)
```

### 2. New Telegram Bot ✅
- Created new bot: `@assistant_clauze_bot`
- Token: `8233548348:AAF-MfrapA4msggPkzuwy75wBaMNrdBsvjQ`
- Configured in OpenClaw

### 3. NVIDIA API Provider ✅
```json
{
  "models": {
    "providers": {
      "nvidia": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "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",
        "api": "openai-completions",
        "models": [{"id": "moonshotai/kimi-k2.5", "name": "Kimi K2.5"}]
      }
    }
  }
}
```

**Result**: Bot working, responds in ~10-20s

---

## CLI Router Development

### Goal
Build a local router to wrap OpenCode CLI and provide faster responses than NVIDIA API.

### Router Features Built
1. ✅ HTTP server on port 4097
2. ✅ OpenAI-compatible `/v1/chat/completions` endpoint
3. ✅ Calls OpenCode CLI: `opencode run -m <model> <prompt>`
4. ✅ Cleans ANSI codes from output
5. ✅ Returns content as ARRAY format: `[{"type": "text", "text": "..."}]`

### Router Code
```python
# Key function: convert_to_openclaw_format
def convert_to_openclaw_format(text_response):
    """Convert plain text to OpenClaw expected format"""
    return [{"type": "text", "text": text_response}]
```

### Testing Router
```bash
# Manual test - WORKS
curl -s -X POST "http://127.0.0.1:4097/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "opencode/kimi-k2.5-free", "messages": [{"role": "user", "content": "Hello"}]}'

# Returns:
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": [{"type": "text", "text": "Hello! How can I help you today?"}]
    }
  }]
}
```

---

## The Mystery: OpenClaw Not Calling Router

### Configuration
```json
{
  "models": {
    "providers": {
      "opencode-local": {
        "baseUrl": "http://127.0.0.1:4097/v1",
        "apiKey": "opencode-free",
        "api": "openai-completions",
        "models": [{"id": "opencode/kimi-k2.5-free", "name": "Kimi"}]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {"primary": "opencode-local/opencode/kimi-k2.5-free"}
    }
  }
}
```

### Expected Behavior
1. OpenClaw receives Telegram message
2. OpenClaw calls `http://127.0.0.1:4097/v1/chat/completions`
3. Router executes OpenCode CLI
4. Router returns response
5. OpenClaw sends reply to Telegram

### Actual Behavior
1. ✅ OpenClaw receives Telegram message
2. ❌ OpenClaw does NOT call router (router debug log is empty)
3. OpenClaw shows `provider=opencode-local` in logs
4. OpenClaw stores empty content `[]` in session
5. No response sent to Telegram

### Debugging Attempted

1. **Added debug logging to router**
   - Logs every HTTP request
   - Log file: `/tmp/router_debug.log`
   - Result: Log stays empty when OpenClaw processes messages

2. **Verified router is reachable**
   ```bash
   curl http://127.0.0.1:4097/v1/models  # Works
   ```

3. **Checked OpenClaw logs**
   - Shows `provider=opencode-local`
   - Shows `model=opencode/kimi-k2.5-free`
   - No connection errors
   - Run completes with `isError=false`
   - Duration: ~4 seconds

4. **Compared NVIDIA vs Local**
   - NVIDIA: Content stored correctly
   - Local: Content is empty `[]`

5. **Tested response format**
   - Tried STRING format: `"content": "Hello!"`
   - Tried ARRAY format: `"content": [{"type": "text", "text": "Hello!"}]`
   - Both result in empty content in OpenClaw

### Hypotheses

1. **OpenClaw has internal fallback**
   - When local provider fails, silently uses something else
   - No error logs to indicate failure

2. **OpenClaw doesn't actually call the provider**
   - Configuration is read but not used
   - Possible bug in OpenClaw provider selection

3. **Network isolation**
   - OpenClaw running in different network context
   - Can't reach 127.0.0.1:4097

4. **API endpoint mismatch**
   - `openai-completions` might require different endpoint
   - Should test with raw OpenAI format

---

## Repository

**GitHub**: https://github.com/IsleOf/wraprouter

**Files:**
- `cli_router.py` - Main router with format conversion
- `CLI_ROUTER.md` - Documentation
- `HANDOVER.md` - Agent handover document

---

## Commands Reference

### SSH to VPS
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

### Check OpenClaw Status
```bash
export PATH=$HOME/.npm-global/bin:$PATH
openclaw gateway status
```

### Switch Providers
```bash
# NVIDIA (working)
openclaw config set agents.defaults.model.primary "nvidia/moonshotai/kimi-k2.5"

# Local router (debugging)
openclaw config set agents.defaults.model.primary "opencode-local/opencode/kimi-k2.5-free"

# Restart
openclaw gateway restart
```

### Test Router
```bash
# Test models endpoint
curl http://127.0.0.1:4097/v1/models

# Test chat
curl -s -X POST "http://127.0.0.1:4097/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "opencode/kimi-k2.5-free", "messages": [{"role": "user", "content": "Hello"}]}'
```

### View Logs
```bash
# OpenClaw logs
tail -f /tmp/openclaw-1000/openclaw-2026-02-17.log

# Router debug log
cat /tmp/router_debug.log

# Session
tail -f ~/.openclaw/agents/main/sessions/58771608-a648-4d92-93c6-74e75af570ce.jsonl
```

---

## File Locations

- **OpenClaw Config**: `~/.openclaw/openclaw.json`
- **OpenClaw Logs**: `/tmp/openclaw-1000/openclaw-2026-02-17.log`
- **Router**: `/home/ubuntu/cli_router.py`
- **Router Debug Log**: `/tmp/router_debug.log`
- **Session**: `~/.openclaw/agents/main/sessions/58771608-a648-4d92-93c6-74e75af570ce.jsonl`

---

## Next Steps

1. **Investigate OpenClaw provider calling**
   - Check if OpenClaw actually attempts HTTP connection
   - Use tcpdump or strace to see network activity
   - Check for connection refused/timeout errors

2. **Alternative: Use opencode serve**
   - `opencode serve --port 4097` provides built-in API
   - Test if OpenClaw can connect to that

3. **Alternative: Use LiteLLM proxy**
   - LiteLLM can wrap CLI tools
   - Provides standard OpenAI API

4. **Debug OpenClaw source**
   - Check how `openai-completions` provider works
   - Look for HTTP client code
   - Find where requests are made

---

**Summary**: Router is built and working correctly when tested manually. OpenClaw shows correct provider in logs but never actually calls the router. This is a blocking issue that needs investigation at the OpenClaw level.

**Working Setup**: NVIDIA API (for now)  
**Goal**: Get local router working for faster responses
