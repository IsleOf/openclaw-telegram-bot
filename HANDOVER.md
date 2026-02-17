# AGENT HANDOVER - OpenClaw Telegram Bot

**Last Updated**: 2026-02-17  
**Current Status**: 🟡 **DEBUGGING** - Router built but OpenClaw not calling it  
**Priority**: HIGH - Investigate why OpenClaw bypasses local router

---

## 🎉 Current Status

**✅ Telegram Bot WORKING via NVIDIA API!**
- Bot: `@assistant_clauze_bot`
- Provider: NVIDIA API (`moonshotai/kimi-k2.5`)
- Status: Responding to messages
- Response time: ~10-20s
- API Key: `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`

**❌ Local Router Issue:**
- Router runs on port 4097 ✓
- Returns correct ARRAY format ✓
- **BUT**: OpenClaw NEVER calls the router (router log is empty)
- OpenClaw shows `provider=opencode-local` but doesn't actually use it

---

## 🔍 CRITICAL DISCOVERY

**The Problem:**
OpenClaw is configured to use `opencode-local` provider with baseUrl `http://127.0.0.1:4097/v1`, but:

1. Router runs on port 4097 and responds correctly ✓
2. OpenClaw logs show `provider=opencode-local` ✓
3. **Router receives NO requests** (debug log is empty) ✗
4. OpenClaw stores empty content `[]` in session

**This means:** OpenClaw is NOT actually calling the router despite being configured to!

---

## 🔧 Router Implementation

**File**: `/home/ubuntu/cli_router.py`

**Router Features:**
- ✅ OpenAI-compatible `/v1/chat/completions` endpoint
- ✅ Returns content as ARRAY: `[{"type": "text", "text": "..."}]`
- ✅ Calls OpenCode CLI with `opencode run -m <model> <prompt>`
- ✅ Cleans ANSI codes and build messages from output
- ✅ Runs on port 4097

**Test Command:**
```bash
curl -s -X POST "http://127.0.0.1:4097/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "opencode/kimi-k2.5-free", "messages": [{"role": "user", "content": "Hello"}]}'
```

**Expected Response:**
```json
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

## 📋 Configuration

### OpenClaw Config (`~/.openclaw/openclaw.json`):
```json
{
  "models": {
    "providers": {
      "opencode-local": {
        "baseUrl": "http://127.0.0.1:4097/v1",
        "apiKey": "opencode-free",
        "api": "openai-completions",
        "models": [
          {"id": "opencode/kimi-k2.5-free", "name": "Kimi K2.5"}
        ]
      },
      "nvidia": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "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",
        "api": "openai-completions",
        "models": [{"id": "moonshotai/kimi-k2.5", "name": "Kimi K2.5"}]
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

### Switch Providers:
```bash
export PATH=$HOME/.npm-global/bin:$PATH

# Use NVIDIA (working)
openclaw config set agents.defaults.model.primary "nvidia/moonshotai/kimi-k2.5"

# Use Local Router (debugging)
openclaw config set agents.defaults.model.primary "opencode-local/opencode/kimi-k2.5-free"

# Restart gateway
openclaw gateway restart
```

---

## 🐛 Debugging Information

### Router Debug Log:
**Location**: `/tmp/router_debug.log`
**Status**: Empty (OpenClaw never calls the router)

### OpenClaw Logs:
**Location**: `/tmp/openclaw-1000/openclaw-2026-02-17.log`
**Shows**: `provider=opencode-local` but no actual HTTP requests to port 4097

### Session File:
**Location**: `~/.openclaw/agents/main/sessions/58771608-a648-4d92-93c6-74e75af570ce.jsonl`
**Shows**: Empty content `[]` for opencode-local provider

### Test if Router is Reachable:
```bash
# Should return model list
curl http://127.0.0.1:4097/v1/models

# Should return chat completion
curl -s -X POST "http://127.0.0.1:4097/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "opencode/kimi-k2.5-free", "messages": [{"role": "user", "content": "test"}]}'
```

---

## 🎯 Hypotheses

1. **OpenClaw has internal fallback**: When opencode-local fails, it silently falls back to something else
2. **API type mismatch**: `openai-completions` might expect different response structure
3. **Network isolation**: OpenClaw might be running in isolated network context
4. **OpenClaw bug**: Provider not actually being called despite configuration

---

## 📝 What We've Tried

1. ✅ Built router with format conversion (STRING → ARRAY)
2. ✅ Router returns correct OpenAI-compatible format
3. ✅ Router tested manually with curl (works perfectly)
4. ✅ Added debug logging to router (log stays empty)
5. ✅ Verified OpenClaw config has correct baseUrl
6. ✅ Confirmed router is listening on 127.0.0.1:4097
7. ❌ OpenClaw still doesn't call the router

---

## 🛠️ Commands for Claude Code

### Check Current Status:
```bash
# Check which provider is active
grep "primary" ~/.openclaw/openclaw.json

# Check router is running
ps aux | grep cli_router
ss -tlnp | grep 4097

# Check router log
cat /tmp/router_debug.log

# Check OpenClaw logs
tail -50 /tmp/openclaw-1000/openclaw-2026-02-17.log | grep -E "opencode-local|agent"
```

### Test Router Manually:
```bash
# Test models endpoint
curl http://127.0.0.1:4097/v1/models

# Test chat completions
curl -s -X POST "http://127.0.0.1:4097/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "opencode/kimi-k2.5-free", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Check Session:
```bash
# View latest session entry
tail -1 ~/.openclaw/agents/main/sessions/58771608-a648-4d92-93c6-74e75af570ce.jsonl | python3 -m json.tool
```

---

## 🎯 Next Steps for Claude Code

1. **Investigate why OpenClaw doesn't call the router**
   - Check if there's a network/firewall issue
   - Verify OpenClaw is actually trying to connect to port 4097
   - Look for connection errors in OpenClaw logs

2. **Test if OpenClaw can reach the router**
   - Use `openclaw agent` command to test local provider directly
   - Check if there's a proxy or network isolation

3. **Compare NVIDIA vs Local provider behavior**
   - NVIDIA works and shows content in session
   - Local shows empty content despite configuration
   - Find the difference in how they're called

4. **Alternative approaches**
   - Use OpenCode's built-in API (`opencode serve`)
   - Configure OpenClaw to use CLI directly instead of HTTP
   - Use a proxy like LiteLLM

---

## 📁 Files

- **Router**: `/home/ubuntu/cli_router.py`
- **Config**: `~/.openclaw/openclaw.json`
- **Logs**: `/tmp/openclaw-1000/openclaw-2026-02-17.log`
- **Router Debug**: `/tmp/router_debug.log`
- **Session**: `~/.openclaw/agents/main/sessions/58771608-a648-4d92-93c6-74e75af570ce.jsonl`

---

## 🔗 Repository

**GitHub**: https://github.com/IsleOf/wraprouter

---

**Summary for Claude Code:**
The router is built and working correctly when tested manually with curl. However, OpenClaw never actually calls the router even though it's configured to use it. The router's debug log remains empty. OpenClaw logs show `provider=opencode-local` but no HTTP requests are made to port 4097. Need to investigate why OpenClaw bypasses or fails to call the local provider.

**Current Working Setup:** NVIDIA API (slow but functional)
**Goal:** Get local router working for faster responses
