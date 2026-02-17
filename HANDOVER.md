# AGENT HANDOVER - OpenClaw Telegram Bot

**Last Updated**: 2026-02-17  
**Current Status**: ✅ **WORKING** - Bot responds via NVIDIA API (slow but functional)  
**Priority**: MEDIUM - Now building CLI Router

---

## 🎉 Current Status

**✅ Telegram Bot WORKING!**
- Bot: `@assistant_clauze_bot`
- Provider: NVIDIA API (`moonshotai/kimi-k2.5`)
- Status: Responding to messages (slow ~10-20s response time)
- API Key: `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`

**✅ Completed Fixes:**
1. Disk space freed (7GB)
2. Bot token configured
3. NVIDIA API provider configured
4. Gateway running with correct model

---

## 🔧 Current Task: Build CLI Router

**Goal**: Create a unified OpenAI-compatible API router that wraps multiple CLI tools:
- OpenCode CLI
- Kilocode CLI  
- Claude Code CLI

**Repository**: https://github.com/IsleOf/wraprouter

### Router Features Needed:
1. ✅ OpenAI-compatible `/v1/chat/completions` endpoint
2. ✅ Model multiplexing (route to correct backend)
3. ⏳ Support for multiple CLI backends
4. ⏳ Error handling & retries
5. ⏳ Request/response logging
6. ⏳ Configuration file support

### Router Architecture:
```
OpenClaw → CLI Router (port 4097) → CLI Tool (OpenCode/Kilocode/Claude)
                ↓
         Standard OpenAI API format
```

---

## 📋 Configuration

### OpenClaw Config Location:
`/home/ubuntu/.openclaw/openclaw.json`

### Current Working Config:
```json
{
  "models": {
    "providers": {
      "nvidia": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "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",
        "api": "openai-completions",
        "models": [
          {
            "id": "moonshotai/kimi-k2.5",
            "name": "Kimi K2.5 (NVIDIA)"
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "nvidia/moonshotai/kimi-k2.5"
      }
    }
  }
}
```

---

## 🛠️ Development Commands

### Check Bot Status:
```bash
export PATH=$HOME/.npm-global/bin:$PATH
openclaw gateway status
```

### View Logs:
```bash
tail -f /tmp/openclaw-1000/openclaw-2026-02-17.log | grep -E "telegram|nvidia|agent"
```

### Test NVIDIA API:
```bash
curl -s https://integrate.api.nvidia.com/v1/models \
  -H "Authorization: Bearer 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"
```

### SSH to VPS:
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

---

## 📝 CLI Router Specification

The router should:

1. **Listen on port 4097** (or configurable)
2. **Accept OpenAI-compatible requests**:
   - POST `/v1/chat/completions`
   - GET `/v1/models`
3. **Route to correct backend** based on model ID:
   - `opencode/*` → OpenCode CLI
   - `kilocode/*` → Kilocode CLI
   - `claude/*` → Claude Code CLI
4. **Convert responses** to OpenAI format:
   - Content as STRING (not array) for openai-completions API
5. **Handle errors gracefully**

### Example Request Flow:
```
OpenClaw sends:
POST /v1/chat/completions
{
  "model": "opencode/kimi-k2.5-free",
  "messages": [{"role": "user", "content": "Hello"}]
}

Router executes:
opencode run -m opencode/kimi-k2.5-free "Hello"

Router returns:
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help?"
    }
  }]
}
```

---

## 🆘 Troubleshooting

**If bot stops responding:**
1. Check gateway: `openclaw gateway status`
2. Check logs: `tail /tmp/openclaw-1000/openclaw-2026-02-17.log`
3. Check NVIDIA API: Test with curl
4. Restart gateway: `openclaw gateway restart`

**Slow responses:**
- NVIDIA API has latency (~10-20s)
- This is normal for free tier
- Consider upgrading or using local models

---

**Next Action**: Continue building CLI Router with multi-backend support
