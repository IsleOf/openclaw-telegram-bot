# CLI Router for OpenClaw

A unified OpenAI-compatible API router that wraps multiple CLI coding tools.

## Supported Backends

- **OpenCode** - opencode run
- **Kilocode** - kilocode run  
- **Claude Code** - claude
- **OpenRouter** - Direct API (for online models)

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   OpenClaw   │────▶│   CLI Router     │────▶│  OpenCode CLI   │
│              │     │  (Port 4097)     │     │  (Local/VPS)    │
└──────────────┘     └──────────────────┘     └─────────────────┘
                            │
                            ▼
                     ┌─────────────────┐
                     │  Claude Code    │
                     └─────────────────┘
```

## Quick Start

```bash
# Start router
python3 cli_router.py

# Test
curl http://localhost:4097/v1/models
```

## Configuration

Edit `~/.config/cli-router/config.json`:

```json
{
  "default_backend": "opencode",
  "backends": {
    "opencode": {
      "type": "cli",
      "command": "opencode run",
      "port": 4098,
      "models": ["opencode/kimi-k2.5-free", "opencode/minimax-m2.5-free"]
    },
    "claude": {
      "type": "cli", 
      "command": "claude --dangerously-skip-permissions",
      "models": ["anthropic/claude-3-5-sonnet"]
    },
    "openrouter": {
      "type": "api",
      "url": "https://openrouter.ai/api/v1",
      "api_key": "sk-or-v1-...",
      "models": ["openai/gpt-4", "anthropic/claude-3-opus"]
    }
  }
}
```

## Features

- ✅ OpenAI-compatible API
- ✅ Model multiplexing (route to correct backend)
- ✅ Streaming support
- ✅ Error handling & retries
- ✅ Request/response logging
- ✅ Hot-reload config

## For OpenClaw Integration

Configure OpenClaw to use:
```json
{
  "models": {
    "providers": {
      "opencode-local": {
        "baseUrl": "http://127.0.0.1:4097/v1",
        "apiKey": "local",
        "models": [
          {"id": "opencode/kimi-k2.5-free"},
          {"id": "anthropic/claude-3-5-sonnet"}
        ]
      }
    }
  }
}
```

## Router Implementation

See `/home/ubuntu/cli_router.py`
