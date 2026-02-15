#!/bin/bash
# OpenClaw Multi-LLM Setup Script

echo "🦞 OpenClaw Multi-LLM Setup Script"
echo "=================================="

# Backup current config
echo "📦 Backing up current config..."
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup.$(date +%Y%m%d_%H%M%S)

# Create enhanced config with all LLM providers
echo "⚙️  Creating enhanced configuration..."
cat > ~/.openclaw/openclaw.json << 'CONFIGEOF'
{
  "meta": {
    "lastTouchedVersion": "2026.2.13",
    "lastTouchedAt": "2026-02-15T15:30:00.000Z"
  },
  "wizard": {
    "lastRunAt": "2026-02-14T19:26:22.900Z",
    "lastRunVersion": "2026.2.13",
    "lastRunCommand": "onboard",
    "lastRunMode": "local"
  },
  "auth": {
    "profiles": {
      "openrouter:default": {
        "provider": "openrouter",
        "mode": "api_key"
      },
      "antigravity:default": {
        "provider": "antigravity",
        "mode": "oauth",
        "enabled": true
      },
      "opencode:default": {
        "provider": "opencode",
        "mode": "api_key",
        "enabled": true,
        "baseUrl": "https://api.opencode.ai/v1"
      },
      "trae:default": {
        "provider": "trae",
        "mode": "api_key",
        "enabled": true,
        "baseUrl": "https://api.trae.ai/v1"
      },
      "kilocode:default": {
        "provider": "kilocode",
        "mode": "api_key",
        "enabled": true,
        "baseUrl": "https://api.kilo.ai/v1"
      },
      "google:default": {
        "provider": "google",
        "mode": "oauth",
        "enabled": true,
        "scopes": [
          "https://www.googleapis.com/auth/gmail.modify",
          "https://www.googleapis.com/auth/calendar"
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "nvidia/moonshotai/kimi-k2.5",
        "fallback": "antigravity/claude-opus-4.5"
      },
      "models": {
        "openrouter/auto": {
          "alias": "OpenRouter"
        },
        "antigravity/claude-opus-4.5": {
          "alias": "Claude Opus 4.5 (Antigravity)",
          "provider": "antigravity:default",
          "model": "claude-opus-4.5"
        },
        "antigravity/claude-sonnet-4.5": {
          "alias": "Claude Sonnet 4.5 (Antigravity)",
          "provider": "antigravity:default",
          "model": "claude-sonnet-4.5"
        },
        "antigravity/gemini-3-pro": {
          "alias": "Gemini 3 Pro (Antigravity)",
          "provider": "antigravity:default",
          "model": "gemini-3-pro"
        },
        "antigravity/gemini-3-flash": {
          "alias": "Gemini 3 Flash (Antigravity)",
          "provider": "antigravity:default",
          "model": "gemini-3-flash"
        },
        "opencode/kimi-k2.5": {
          "alias": "Kimi K2.5 (Opencode)",
          "provider": "opencode:default",
          "model": "kimi-k2.5"
        },
        "trae/default": {
          "alias": "Trae AI",
          "provider": "trae:default",
          "model": "default"
        },
        "kilocode/default": {
          "alias": "Kilo Code",
          "provider": "kilocode:default",
          "model": "default"
        }
      },
      "workspace": "/home/ubuntu/.openclaw/workspace",
      "compaction": {
        "mode": "safeguard"
      },
      "maxConcurrent": 4,
      "subagents": {
        "maxConcurrent": 8
      }
    }
  },
  "messages": {
    "ackReactionScope": "group-mentions"
  },
  "commands": {
    "native": "auto",
    "nativeSkills": "auto"
  },
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "boot-md": {
          "enabled": true
        },
        "bootstrap-extra-files": {
          "enabled": true
        },
        "command-logger": {
          "enabled": true
        },
        "session-memory": {
          "enabled": true
        }
      }
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "dmPolicy": "pairing",
      "botToken": "8573345722:AAFU5BUISq4j7HOAI2x7NvblVDRtVC30Vyc",
      "groupPolicy": "allowlist",
      "streamMode": "partial"
    }
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "loopback",
    "auth": {
      "mode": "token",
      "token": "4272baca0ae5b42729b6db36a633745511a0cdfa9e9db8b6"
    },
    "tailscale": {
      "mode": "off",
      "resetOnExit": false
    },
    "nodes": {
      "denyCommands": [
        "camera.snap",
        "camera.clip",
        "screen.record"
      ]
    }
  },
  "plugins": {
    "entries": {
      "telegram": {
        "enabled": true
      }
    }
  },
  "tools": {
    "gmail": {
      "enabled": true,
      "authProfile": "google:default"
    },
    "calendar": {
      "enabled": true,
      "authProfile": "google:default"
    }
  }
}
CONFIGEOF

echo "✅ Configuration created!"

# Install Antigravity auth plugin
echo "📥 Installing Antigravity auth plugin..."
npm install -g opencode-antigravity-auth 2>/dev/null || echo "Note: Antigravity plugin may require manual setup"

# Install gogcli for Google OAuth
echo "📥 Installing gogcli for Google OAuth..."
npm install -g gogcli 2>/dev/null || echo "Note: gogcli may require manual setup"

echo ""
echo "🎉 Setup complete! Next steps:"
echo "1. Restart OpenClaw gateway: openclaw gateway restart"
echo "2. Authenticate with Antigravity: opencode-antigravity-auth setup"
echo "3. Authenticate with Google: gogcli auth login"
echo "4. List available models: openclaw models list"
