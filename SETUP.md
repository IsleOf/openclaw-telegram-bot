# Setup Guide — OpenClaw Telegram Bot on AWS VPS

This guide builds the full system from scratch: an AI Telegram bot running on an AWS VPS, using OpenClaw as the agent framework, OpenCode CLI for free-tier LLM access, and a custom Python router that bridges them.

**Time to complete**: ~60–90 minutes
**Cost**: Free (AWS free tier + OpenCode free tier)

---

## Overview of what you're building

```
You (Telegram) → Telegram API → OpenClaw Gateway → CLI Router v5 → OpenCode CLI → Free LLM
```

- **OpenClaw**: Manages the bot's Telegram connection, agent identity, memory, tools, and heartbeat
- **OpenCode CLI**: Authenticates with free LLM providers (GLM-5, MiniMax, etc.) without API keys
- **CLI Router v5** (`cli_router.py`): Custom Python HTTP server that:
  - Receives OpenClaw's ~48KB requests
  - Detects user intent (news, web search, etc.)
  - Pre-executes web tools before calling the LLM
  - Compresses the context and calls `opencode run`
  - Returns the response as SSE stream

---

## Prerequisites

- **AWS account** with EC2 access (free tier works)
- **Telegram account** to create a bot
- **Tailscale account** (free) for secure SSH access
- **GitHub account** for SSH key management (optional but easy)

---

## Step 1: Launch AWS EC2 Instance

### 1.1 Create the instance

1. Go to EC2 → Launch Instance
2. **Name**: `openclaw-bot` (or anything)
3. **AMI**: Ubuntu Server 24.04 LTS (or 22.04)
4. **Instance type**: `t3.micro` (free tier eligible)
5. **Key pair**: Create new → ed25519 → download `.pem` file
6. **Security group**: Allow SSH (port 22) from your IP
7. **Storage**: 20GB gp3 (default is fine)
8. Launch

Note your instance's **Public IPv4 address** from the EC2 console.

### 1.2 Connect initially

```bash
# Using the downloaded .pem key
chmod 400 ~/Downloads/your-key.pem
ssh -i ~/Downloads/your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

### 1.3 (Recommended) Convert to ed25519 key for daily use

On your **local machine**, if you don't already have an ed25519 key:
```bash
ssh-keygen -t ed25519 -C "your-email"
# Creates ~/.ssh/id_ed25519 and ~/.ssh/id_ed25519.pub
```

Add your public key to the VPS:
```bash
# From your local machine (replace IP and pem path)
cat ~/.ssh/id_ed25519.pub | ssh -i ~/Downloads/your-key.pem ubuntu@<EC2-PUBLIC-IP> \
  "cat >> ~/.ssh/authorized_keys"
```

Now you can SSH without the pem file:
```bash
ssh ubuntu@<EC2-PUBLIC-IP>
```

---

## Step 2: Install Tailscale (Recommended)

Tailscale provides a stable private IP that doesn't change even when the EC2 instance is restarted (unlike public IPs unless you use an Elastic IP).

### 2.1 On the VPS

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Follow the link shown to authenticate with your Tailscale account
```

After authentication, note the Tailscale IP (100.x.x.x):
```bash
tailscale ip -4
```

### 2.2 On your local machine

Install Tailscale for your OS from [tailscale.com/download](https://tailscale.com/download) and sign in with the same account.

Now you can SSH via the Tailscale IP permanently:
```bash
ssh ubuntu@<TAILSCALE-IP>
```

### ⚠️ Critical Warning

**Never run `tailscale set --exit-node=...` on the VPS.** If you route the VPS's traffic through an exit node and that node goes offline, the VPS becomes completely unreachable — SSH stops working and it persists through reboots.

Recovery if this happens: AWS EC2 console → Instance Settings → Edit User Data → Add:
```bash
#!/bin/bash
tailscale set --exit-node=
```
Then stop and start (not reboot) the instance.

---

## Step 3: Install System Dependencies

SSH into the VPS and run all commands below as `ubuntu`.

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Python pip and venv
sudo apt-get install -y python3-pip python3-venv

# Node.js 20 (required for OpenClaw)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify versions
node --version    # should be v20+
python3 --version # should be 3.10+
```

---

## Step 4: Install OpenCode CLI

OpenCode provides free access to LLMs via its "Antigravity" auth without needing API keys. You authenticate once with GitHub.

```bash
curl -fsSL https://opencode.ai/install | bash
# This installs to ~/.opencode/bin/opencode
```

Authenticate (uses GitHub OAuth):
```bash
~/.opencode/bin/opencode auth
# Opens a browser link — paste in browser, sign in with GitHub
```

Verify it works:
```bash
~/.opencode/bin/opencode run -m opencode/minimax-m2.5-free "say hi"
# Should respond within 5-10 seconds
```

Check available free models:
```bash
~/.opencode/bin/opencode models | grep -i free
```

Add opencode to PATH (add to `~/.bashrc` or `~/.profile`):
```bash
echo 'export PATH="$HOME/.opencode/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Step 5: Create Telegram Bot

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Follow prompts: choose a name and username (must end in `bot`)
4. **Copy the bot token** — you'll need it for OpenClaw config

Optional: Set bot commands via BotFather for a nice menu.

---

## Step 6: Install OpenClaw

```bash
# Install globally
npm install -g openclaw

# Verify
npx openclaw --version
```

Run first-time setup:
```bash
npx openclaw setup
```

This creates `~/.openclaw/` with default config, workspace, etc.

---

## Step 7: Configure OpenClaw

Edit `~/.openclaw/openclaw.json`. Replace the entire file with:

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
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN_HERE",
      "dmPolicy": "open",
      "streamMode": "partial"
    }
  },
  "heartbeat": {
    "every": "60m",
    "target": "last",
    "activeHours": {"start": "07:00", "end": "23:00"}
  }
}
```

Replace `YOUR_BOT_TOKEN_HERE` with the token from BotFather.

Validate the config:
```bash
npx openclaw doctor --fix
```

---

## Step 8: Set Up Agent Workspace

These files define the bot's identity, personality, and instructions.

### 8.1 IDENTITY.md — Who the agent is

```bash
cat > ~/.openclaw/workspace/IDENTITY.md << 'EOF'
# Identity

Name: Claw
Emoji: 🦞
Role: Personal AI assistant

You are direct, resourceful, and a little irreverent. You get things done.
EOF
```

### 8.2 USER.md — Who the user is

```bash
cat > ~/.openclaw/workspace/USER.md << 'EOF'
# User

Name: [Your Name]
Telegram: @yourusername
Language: English (adapt if they write in another language)
Timezone: [Your timezone, e.g. UTC+2]

Context:
- [Add relevant context about the user, projects, preferences]
EOF
```

Edit this with your actual details.

### 8.3 SOUL.md — Personality

```bash
cat > ~/.openclaw/workspace/SOUL.md << 'EOF'
# Soul

Core traits:
- Genuine and direct — says what it thinks, not what sounds nice
- Resourceful — finds ways to get things done with what's available
- Trustworthy — accurate, admits uncertainty, doesn't hallucinate confidently
- Concise — one good answer beats three hedged paragraphs

Communication style:
- Short sentences. No fluff.
- Uses "I" naturally, not "As an AI..."
- Gives opinions when asked
- Adapts tone to the conversation (can be playful, can be serious)
EOF
```

### 8.4 MEMORY.md — Long-term memory

```bash
mkdir -p ~/.openclaw/workspace/memory
cat > ~/.openclaw/workspace/memory/MEMORY.md << 'EOF'
# Memory

## User Info
[Fill in as you learn about the user]

## Key Projects
[Add ongoing projects here]

## Preferences
[Things the user likes / dislikes]

## Session Notes
[Add dated notes from conversations]
EOF
```

### 8.5 TODOS.md — Task list

```bash
cat > ~/.openclaw/workspace/TODOS.md << 'EOF'
# TODOS

## Active
- [ ] (add tasks here)

## Completed
EOF
```

### 8.6 AGENTS.md — Operational instructions

This is the most important file — it tells the agent how to behave on this VPS.

```bash
cat > ~/.openclaw/workspace/AGENTS.md << 'EOF'
# Agent Instructions

## Startup
1. Read MEMORY.md for context
2. Check TODOS.md for pending tasks
3. Be ready to help

## Rules
- Do tasks, don't describe what you could do
- Be concise — Telegram has no word limit but the user's patience does
- When asked for news or search results, actually fetch them
- Admit when you don't know something

## Web Browsing
You have these web tools available via exec:

### Search the web
```bash
python3 ~/.openclaw/workspace/skills/web-browser/scripts/web_search.py \
  --query "your search query" --max-results 5
```
Returns: JSON array of {title, url, snippet}

### Fetch a page
```bash
python3 ~/.openclaw/workspace/skills/web-browser/scripts/web_fetch.py \
  --url "https://example.com" --max-chars 5000
```
Returns: readable text from the page

## Memory Management
- Update MEMORY.md when learning important new information about the user
- Add completed tasks to TODOS.md's Completed section

## Heartbeat
When triggered on schedule, check:
1. Is disk usage under 80%? (df -h /)
2. Are router and gateway running? (ss -tlnp | grep -E '4097|18789')
3. Any urgent items in TODOS.md?
Report findings or log HEARTBEAT_OK if nothing needs attention.

## Group Chat Behavior
- Only respond when directly mentioned or clearly addressed
- Stay on topic for the group
- Keep responses shorter than in DMs
EOF
```

---

## Step 9: Install Web Browser Skill

The web browser skill provides search and page-fetching capabilities.

### 9.1 Create skill directory structure

```bash
mkdir -p ~/.openclaw/workspace/skills/web-browser/scripts
```

### 9.2 Install Python dependencies

```bash
pip3 install duckduckgo-search playwright
playwright install chromium
playwright install-deps chromium
```

### 9.3 Create web_search.py

```bash
cat > ~/.openclaw/workspace/skills/web-browser/scripts/web_search.py << 'PYEOF'
#!/usr/bin/env python3
"""DuckDuckGo web search. Returns JSON array of {title, url, snippet}."""
import argparse, json, sys
from duckduckgo_search import DDGS

parser = argparse.ArgumentParser()
parser.add_argument('--query', required=True)
parser.add_argument('--max-results', type=int, default=5)
args = parser.parse_args()

try:
    with DDGS() as ddgs:
        results = list(ddgs.text(args.query, max_results=args.max_results))
    output = [{'title': r.get('title',''), 'url': r.get('href',''), 'snippet': r.get('body','')} for r in results]
    print(json.dumps(output, ensure_ascii=False, indent=2))
except Exception as e:
    print(json.dumps([{'error': str(e)}]))
PYEOF
chmod +x ~/.openclaw/workspace/skills/web-browser/scripts/web_search.py
```

### 9.4 Create web_fetch.py

```bash
cat > ~/.openclaw/workspace/skills/web-browser/scripts/web_fetch.py << 'PYEOF'
#!/usr/bin/env python3
"""Fetch a URL and return readable text content using Playwright."""
import argparse, sys, re
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True)
parser.add_argument('--max-chars', type=int, default=5000)
args = parser.parse_args()

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        page.goto(args.url, timeout=30000, wait_until='domcontentloaded')
        text = page.inner_text('body')
        browser.close()
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    print(text[:args.max_chars])
except Exception as e:
    print(f'Error fetching {args.url}: {e}', file=sys.stderr)
    sys.exit(1)
PYEOF
chmod +x ~/.openclaw/workspace/skills/web-browser/scripts/web_fetch.py
```

### 9.5 Create SKILL.md (OpenClaw skill manifest)

```bash
cat > ~/.openclaw/workspace/skills/web-browser/SKILL.md << 'EOF'
---
name: web-browser
description: Browse the web, search for information, and read web pages.
metadata: { "openclaw": { "emoji": "🌐", "requires": { "bins": ["python3"] } } }
---

# Web Browser

## Search the Web
```bash
python3 skills/web-browser/scripts/web_search.py --query "your query" --max-results 5
```

## Fetch Page Content
```bash
python3 skills/web-browser/scripts/web_fetch.py --url "https://example.com" --max-chars 5000
```
EOF
```

### 9.6 Test the skill

```bash
# Test search
python3 ~/.openclaw/workspace/skills/web-browser/scripts/web_search.py \
  --query "Estonia news today" --max-results 3

# Test fetch
python3 ~/.openclaw/workspace/skills/web-browser/scripts/web_fetch.py \
  --url "https://www.err.ee/uudised" --max-chars 1000
```

Both should return results without errors.

---

## Step 10: Deploy CLI Router v5

The router is the glue between OpenClaw and OpenCode. Copy `cli_router.py` from this repository to the VPS.

### 10.1 Copy the router

From your **local machine**:
```bash
scp cli_router.py ubuntu@<TAILSCALE-IP>:/home/ubuntu/cli_router.py
```

Or from the VPS directly (if you've pushed to GitHub):
```bash
wget -O /home/ubuntu/cli_router.py \
  https://raw.githubusercontent.com/YOUR_GITHUB/openclaw-telegram-bot/main/cli_router.py
```

### 10.2 Create systemd service for the router

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/openclaw-router.service << 'EOF'
[Unit]
Description=OpenClaw CLI Router v5
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/ubuntu/cli_router.py
Restart=always
RestartSec=3
Environment=PATH=/home/ubuntu/.opencode/bin:/usr/local/bin:/usr/bin:/bin
Environment=ROUTER_MODEL=opencode/minimax-m2.5-free
Environment=ROUTER_TIMEOUT=300
Environment=ROUTER_PORT=4097

[Install]
WantedBy=default.target
EOF
```

Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-router
systemctl --user start openclaw-router
systemctl --user status openclaw-router
```

You should see `Active: active (running)`.

### 10.3 Test the router

```bash
# Check it's listening
ss -tlnp | grep 4097

# Test models endpoint
curl -s http://localhost:4097/v1/models

# Test a simple completion (no streaming)
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"say hello"}]}'
```

The last command should return a JSON response with the model's greeting (takes 5–15s).

---

## Step 11: Start OpenClaw Gateway

### 11.1 Create systemd service for the gateway

```bash
cat > ~/.config/systemd/user/openclaw-gateway.service << 'EOF'
[Unit]
Description=OpenClaw Gateway
After=network.target openclaw-router.service

[Service]
ExecStart=/usr/bin/npx openclaw gateway
Restart=always
RestartSec=5
WorkingDirectory=/home/ubuntu
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF
```

Enable and start:
```bash
systemctl --user enable openclaw-gateway
systemctl --user start openclaw-gateway
sleep 3
systemctl --user status openclaw-gateway
```

### 11.2 Enable lingering (so services run after SSH logout)

```bash
sudo loginctl enable-linger ubuntu
```

This ensures the systemd user services keep running even when you're not SSH'd in.

### 11.3 Verify gateway is up

```bash
ss -tlnp | grep 18789   # gateway port
tail -10 /tmp/openclaw/openclaw-*.log  # gateway logs
```

The log should show the agent model being loaded and Telegram connected.

---

## Step 12: Test the Bot

### 12.1 On the router

```bash
# Watch logs in real time
tail -f /tmp/router_debug.log
```

In another terminal or Telegram, send a message to the bot.

### 12.2 From Telegram

Open Telegram, find your bot by its username, and send:

1. `hello` — should reply within 5–10s
2. `what is 7 * 8` — should reply `56` quickly
3. `tell me Estonian news for today` — should reply with actual headlines in ~35s
4. `search for best coffee in Tallinn` — should return DuckDuckGo results

### 12.3 Common issues

| Symptom | Check |
|---------|-------|
| No reply at all | `ss -tlnp \| grep -E '4097\|18789'` — are both ports open? |
| Bot says "taking too long" | Router timeout hit (300s default). Check `tail -20 /tmp/router_debug.log` |
| Bot lists capabilities instead of acting | Router not running — check `systemctl --user status openclaw-router` |
| Bot lists capabilities on news queries | Intent detection not matching — check the exact message matches keywords |

---

## Step 13: Optional — Cron Jobs

Add scheduled tasks to OpenClaw (inside `openclaw.json`, under `"crons"`):

```json
"crons": [
  {
    "name": "Morning Briefing",
    "cron": "0 8 * * *",
    "prompt": "It's morning. Check the weather for Tallinn, give me a brief news summary, and list today's TODOS."
  },
  {
    "name": "System Check",
    "cron": "0 */6 * * *",
    "prompt": "Run a system check: disk usage (df -h /), memory (free -h), and confirm router and gateway are on ports 4097 and 18789."
  },
  {
    "name": "Estonian News",
    "cron": "0 */12 * * *",
    "prompt": "Fetch the latest Estonian news headlines from ERR.ee or Postimees and summarise the top stories."
  }
]
```

After editing `openclaw.json`, restart the gateway:
```bash
systemctl --user restart openclaw-gateway
```

---

## Step 14: Maintenance

### Update the router

Edit `cli_router.py` locally, then:
```bash
scp cli_router.py ubuntu@<TAILSCALE-IP>:/home/ubuntu/cli_router.py
ssh ubuntu@<TAILSCALE-IP> "systemctl --user restart openclaw-router"
```

### Monitor disk usage

The OpenClaw/Playwright stack can leak `.fbd*.so` files in `/tmp`. Add a cron job to clean them:
```bash
# Add to ubuntu's crontab (crontab -e)
0 * * * * find /tmp -name '*.fbd*.so' -mmin +60 -delete 2>/dev/null
```

### Change the model

Edit `ROUTER_MODEL` in the systemd service or `openclaw.json`. Available options:
- `opencode/minimax-m2.5-free` — large context, good synthesis
- `opencode/glm-5-free` — better instruction-following
- `opencode/trinity-large-preview-free` — experimental

After changing systemd env, run:
```bash
systemctl --user daemon-reload && systemctl --user restart openclaw-router
```

### View all logs

```bash
# Router (recent activity)
tail -50 /tmp/router_debug.log

# Gateway
ls /tmp/openclaw/
tail -30 /tmp/openclaw/openclaw-*.log

# Systemd service status
systemctl --user status openclaw-router openclaw-gateway --no-pager
```

---

## Architecture Notes

### Why not use OpenClaw's built-in model providers directly?

OpenClaw supports OpenAI, Anthropic, NVIDIA, and others directly. We use a local router instead because:
1. OpenCode's Antigravity free tier is the only truly free option with no usage caps
2. OpenCode CLI requires being invoked as a subprocess, not via HTTP API
3. The router bridges this gap while handling prompt compression and tool pre-execution

### Why pre-execute tools instead of relying on the model?

Free-tier LLMs (especially GLM-5, MiniMax) are unreliable at native tool calling (emitting JSON function calls). When asked to search the web, they often describe what they'd do instead of doing it. The router solves this by:
- Detecting intent from the user message
- Running the tools itself (web search, page fetch)
- Injecting the real results into the prompt
- Having the LLM just synthesize/format the results

This is more reliable than hoping the model calls the right tool correctly.

### Why SSE streaming is required

OpenClaw uses the OpenAI JavaScript SDK which always sends `stream: true`. The router must return `text/event-stream` format. Any provider that returns plain JSON will have its responses silently discarded by OpenClaw.
