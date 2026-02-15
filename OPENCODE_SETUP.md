# OpenCode on AWS Server - Complete Setup

## Status: ✅ Running

- **OpenCode Server**: `http://100.93.10.110:4096`
- **SSH Access**: `ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110`

---

## Available Free Models

| Model | Provider | Status |
|-------|----------|--------|
| `opencode/kimi-k2.5-free` | OpenCode | ✅ Working |
| `opencode/minimax-m2.5-free` | OpenCode | ✅ Working |
| `google/antigravity-gemini-3-pro` | Google Antigravity | 🔐 Needs Auth |
| `google/antigravity-gemini-3-flash` | Google Antigravity | 🔐 Needs Auth |
| `google/antigravity-claude-opus-4.5` | Google Antigravity | 🔐 Needs Auth |
| `google/antigravity-claude-sonnet-4.5` | Google Antigravity | 🔐 Needs Auth |

---

## Connect via SSH

```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

---

## Run OpenCode Commands

```bash
# List all models
opencode models

# Run with free model
opencode run -m opencode/kimi-k2.5-free "Hello"

# Start server (already running)
opencode serve --port 4096

# Check server status
curl http://100.93.10.110:4096/
```

---

## Authentication for Antigravity (Free Claude/Gemini)

To use free Claude Opus 4.5 and Gemini 3 Pro:

**On your LOCAL machine**, run:
```bash
# Install OpenCode locally
curl -fsSL https://opencode.ai/install | bash

# Authenticate with Google
opencode auth login
```

Then select:
1. **Google** provider
2. **Add account** 
3. Login with your Google account (must have Antigravity access)

After authentication, the credentials are saved. You can copy the auth file to the server:
```bash
# Copy auth to server
scp -i ~/.ssh/tailscale_key ~/.config/opencode/opencode.json ubuntu@100.93.10.110:~/.config/opencode/
```

---

## Integration with OpenClaw

OpenClaw can now use OpenCode as a model provider by connecting to:
- `http://100.93.10.110:4096` (via Tailscale)

Or via SSH tunnel from your local machine:
```bash
ssh -i ~/.ssh/tailscale_key -L 4096:127.0.0.1:4096 -N -f ubuntu@100.93.10.110
# Then access OpenCode at http://localhost:4096
```

---

## Quick Test

```bash
# SSH to server
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110

# Run test
export PATH=$HOME/.opencode/bin:$PATH
opencode run -m opencode/kimi-k2.5-free "What is 2+2?"
```

---

## Documentation Files

- `/home/dev/openclaw controller/COMPLETE_SETUP.md` - OpenClaw setup
- `/home/dev/openclaw controller/TAILSCALE_SETUP.md` - Tailscale config
- `/home/dev/openclaw controller/PROJECT_HANDBOOK.md` - Project docs
