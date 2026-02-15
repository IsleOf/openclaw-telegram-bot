# OpenClaw VPS Setup - Complete Journey Documentation

## Date: 2026-02-16
## Author: AI Agent via OpenCode

---

## Overview

This document chronicles the complete setup of an autonomous OpenClaw AI agent on an AWS VPS, connecting through Telegram, using Tailscale for remote access, and integrating free LLM models from OpenCode.

---

## 1. AWS Server Setup

### Server Details
- **Public IP**: 3.106.138.96
- **Instance**: ip-172-31-36-81.ap-southeast-2.compute.internal
- **SSH Key**: openclaw_serverr.pem
- **User**: ubuntu

### Initial Connection
```bash
ssh -i "C:\Users\PC\Downloads\openclaw_serverr.pem" ubuntu@3.106.138.96
```

---

## 2. Tailscale Setup (For Autonomous Agent Access)

### Problem
- SSH keys couldn't be shared with AI agent for security reasons
- Needed a way for AI agent to access the VPS autonomously

### Solution: Tailscale VPN

#### On AI Agent Side (This Environment):
```bash
# Add Tailscale repository
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg > /dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt-get update
sudo apt-get install -y tailscale

# Connect and get auth URL
sudo tailscale up
# Provided URL: https://login.tailscale.com/a/10ecc57501855f
```

#### On AWS Server Side:
```bash
# Already had Tailscale installed
tailscale ip -4
# Output: 100.93.10.110
```

#### SSH Key Exchange (For Passwordless Access):
On AWS server:
```bash
mkdir -p ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDtkUZLTUsJbVtHgHo3Wi3Wrw7lrgwt0qapuW9aoL/Oz dev@DESKTOP-F3V5NK7" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

#### Final Connection:
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

---

## 3. OpenClaw Installation

### On AWS Server:
```bash
# Install OpenClaw
curl -fsSL https://openclaw.ai/install.sh | bash

# Initial setup
openclaw onboard --install-daemon

# Add to PATH
export PATH="$HOME/.npm-global/bin:$PATH"
```

---

## 4. OpenCode Server Setup (Free LLM Models)

### Installation:
```bash
# Install OpenCode
curl -fsSL https://opencode.ai/install | bash

# Start server on port 4096
export PATH=$HOME/.opencode/bin:$PATH
opencode serve --port 4096 --hostname 0.0.0.0
```

### Available Free Models:
- `opencode/kimi-k2.5-free`
- `opencode/minimax-m2.5-free`
- `google/antigravity-claude-opus-4.5` (requires auth)
- `google/antigravity-gemini-3-pro` (requires auth)

---

## 5. OpenClaw Configuration

### Working Config (YAML format):
```json
{
  "meta": {
    "lastTouchedVersion": "2026.2.13",
    "lastTouchedAt": "2026-02-16T01:00:00.000Z"
  },
  "auth": {
    "profiles": {
      "openrouter:default": {
        "provider": "openrouter",
        "mode": "api_key"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "openrouter/quickie-ai/minimax-m2.5-free"
      },
      "models": {
        "openrouter/quickie-ai/minimax-m2.5-free": {
          "alias": "MiniMax M2.5 Free"
        },
        "openrouter/auto": {
          "alias": "OpenRouter Auto"
        }
      },
      "workspace": "/home/ubuntu/.openclaw/workspace"
    }
  },
  "tools": {
    "exec": {
      "host": "gateway",
      "security": "full",
      "ask": "off"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "dmPolicy": "open",
      "allowFrom": ["*"],
      "botToken": "8573345722:AAFU5BUISq4j7HOAI2x7NvblVDRtVC30Vyc"
    }
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "auth": {
      "mode": "token",
      "token": "4272baca0ae5b42729b6db36a633745511a0cdfa9e9db8b6"
    }
  },
  "plugins": {
    "entries": {
      "telegram": {
        "enabled": true
      }
    }
  }
}
```

### Setting Model via CLI:
```bash
openclaw config set agents.defaults.model.primary openrouter/quickie-ai/minimax-m2.5-free
openclaw gateway restart
```

---

## 6. Exec Permissions (Full Autonomous Mode)

### Exec Approvals Config (`~/.openclaw/exec-approvals.json`):
```json
{
  "version": 1,
  "defaults": {
    "security": "full",
    "ask": "off",
    "askFallback": "allow",
    "autoAllowSkills": true
  },
  "agents": {
    "main": {
      "security": "full",
      "ask": "off",
      "allowlist": []
    }
  }
}
```

### Session-Level Override (via Telegram):
```
/exec host=gateway security=full ask=off
```

---

## 7. Troubleshooting Commands

### Check Status:
```bash
openclaw gateway status
```

### View Logs:
```bash
openclaw logs --follow
tail -f /tmp/openclaw/openclaw-2026-02-15.log
```

### Fix Config:
```bash
openclaw doctor --fix
openclaw gateway restart
```

### Test Model:
```bash
openclaw models list
```

---

## 8. Key Learnings

### Issues Encountered:
1. **SSH Key Security**: Cannot share private SSH keys with AI agent
   - Solution: Use Tailscale VPN + pre-shared SSH key

2. **OpenClaw Config Schema**: Many config keys are unrecognized
   - Solution: Use `openclaw doctor --fix` to auto-remove invalid keys
   - Use CLI commands like `openclaw config set` instead of manual JSON

3. **Model Provider**: OpenCode models need proper auth profile
   - Solution: Use OpenRouter for free models instead

4. **Telegram Web**: Clock icon issue - messages stuck in pending
   - Solution: Use incognito mode or different browser

5. **Exec Permissions**: Agent wouldn't run commands
   - Solution: Set `/exec host=gateway security=full ask=off` via Telegram

### Available Free Models:
- **OpenRouter**: `openrouter/quickie-ai/minimax-m2.5-free`
- **OpenCode**: `opencode/kimi-k2.5-free`, `opencode/minimax-m2.5-free`

---

## 9. File Locations

| File | Path |
|------|------|
| OpenClaw Config | `~/.openclaw/openclaw.json` |
| Exec Approvals | `~/.openclaw/exec-approvals.json` |
| OpenClaw Logs | `/tmp/openclaw/openclaw-2026-02-15.log` |
| Workspace | `~/.openclaw/workspace/` |
| OpenCode Config | `~/.config/opencode/opencode.json` |

---

## 10. Quick Reference

### Connect to Server:
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

### Restart OpenClaw:
```bash
export PATH=$HOME/.npm-global/bin:$PATH
openclaw gateway restart
```

### Check Models:
```bash
export PATH=$HOME/.npm-global/bin:$PATH
openclaw models list
```

---

## 11. Future Enhancements Needed

1. **Voice/Whisper**: Install local Whisper for audio transcription
2. **Browser Automation**: Configure Playwright instead of Brave API
3. **Proactive Mode**: Set up heartbeat and cron jobs for autonomous operation
4. **More Free Models**: Configure Antigravity OAuth for Claude/Gemini access
