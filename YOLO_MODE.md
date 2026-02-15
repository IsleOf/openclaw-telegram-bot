# OpenClaw VPS - YOLO Mode Configuration

## Status: ✅ Running

### Access Info
- **SSH**: `ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110`
- **OpenClaw**: Via Telegram or SSH tunnel

---

## YOLO/Full Permissions Config

### exec-approvals.json (Full Access)
```json
{
  "version": 1,
  "defaults": {
    "security": "full",
    "ask": "off",
    "askFallback": "allow",
    "autoAllowSkills": true
  }
}
```

### openclaw.json (Key Settings)
- `tools.exec.security`: "full" - Allows all commands
- `tools.exec.ask`: "off" - No approval prompts
- `channels.telegram.dmPolicy`: "open" - Anyone can DM
- `channels.telegram.allowFrom`: ["*"] - No restrictions

---

## Available Tools

### System Commands
The agent can now run any system command on the VPS:
- `ls`, `cat`, `grep`, `find` - File operations
- `curl`, `wget` - Download files
- `git` - Version control
- `npm`, `pip`, `python` - Package management
- Any installed CLI tool

### Playwright (Browser Automation)
Installed globally via npm. Use via:
```bash
npx playwright [command]
```

### OpenCode Server
- Running on port 4096
- Free models: `opencode/kimi-k2.5-free`, `opencode/minimax-m2.5-free`

---

## Telegram Usage

1. Find bot: `8573345722:AAFU5BUISq4j7HOAI2x7NvblVDRtVC30Vyc`
2. Send message - now unrestricted
3. Agent can:
   - Run any command on VPS
   - Use Playwright for web browsing
   - Access OpenCode free models

---

## Commands to Test

Try sending to Telegram bot:
```
Run "ls -la /home/ubuntu" on the server
```

Or:
```
Browse to https://example.com and tell me what you see
```

---

## Security Warning ⚠️

This is YOLO mode - NO restrictions. Only use on trusted networks!
