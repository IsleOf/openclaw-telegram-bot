# OpenClaw Telegram Bot — Operations Handbook

Quick reference for day-to-day operations.

---

## Server

| Item | Value |
|------|-------|
| VPS | AWS EC2 ap-southeast-2 |
| Tailscale IP | 100.93.10.110 |
| Public IP | 3.106.138.96 |
| SSH | `ssh ubuntu@100.93.10.110` |
| Telegram bot | `@assistant_clauze_bot` |

---

## Services

| Service | Port | Systemd unit |
|---------|------|-------------|
| CLI Router v5 | 4097 | `openclaw-router.service` |
| OpenClaw Gateway | 18789 | `openclaw-gateway.service` |

Both are user-level systemd services (no `sudo` needed).

---

## Common Commands

### SSH into VPS
```bash
ssh ubuntu@100.93.10.110
```

### Check both services are up
```bash
systemctl --user status openclaw-router openclaw-gateway --no-pager
ss -tlnp | grep -E '4097|18789'
```

### Restart everything
```bash
systemctl --user restart openclaw-router openclaw-gateway
```

### View router log (live)
```bash
tail -f /tmp/router_debug.log
```

### View gateway log
```bash
tail -30 /tmp/openclaw/openclaw-*.log
```

### Test router directly
```bash
curl -s -X POST http://localhost:4097/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"opencode/minimax-m2.5-free","stream":false,
       "messages":[{"role":"user","content":"hello"}]}'
```

### Deploy updated router from local
```bash
# Run from local machine
scp "/home/dev/openclaw controller/cli_router.py" ubuntu@100.93.10.110:/home/ubuntu/cli_router.py
ssh ubuntu@100.93.10.110 "systemctl --user restart openclaw-router"
```

### Check disk usage
```bash
df -h /
# Alert if >80% — check /tmp for .fbd*.so files
du -sh /tmp/*.so 2>/dev/null | sort -rh | head -10
```

### Clean leaked tmp files (if disk fills up)
```bash
find /tmp -name '*.fbd*.so' -mmin +60 -delete
```

---

## Model Management

### Current model
`opencode/minimax-m2.5-free` (set in systemd service `Environment=ROUTER_MODEL=...`)

### Available free models
```bash
~/.opencode/bin/opencode models | grep free
```

### Switch model temporarily (until restart)
```bash
ROUTER_MODEL=opencode/glm-5-free python3 /home/ubuntu/cli_router.py
```

### Switch model permanently
Edit `~/.config/systemd/user/openclaw-router.service`:
```ini
Environment=ROUTER_MODEL=opencode/glm-5-free
```
Then:
```bash
systemctl --user daemon-reload && systemctl --user restart openclaw-router
```

---

## OpenClaw Config

**Location**: `~/.openclaw/openclaw.json`

After editing, validate with:
```bash
npx openclaw doctor --fix
```
Then restart gateway:
```bash
systemctl --user restart openclaw-gateway
```

---

## Workspace Files

All in `~/.openclaw/workspace/`:

| File | Purpose | Edit when |
|------|---------|-----------|
| `IDENTITY.md` | Agent name/persona | Changing agent identity |
| `USER.md` | User context | User details change |
| `SOUL.md` | Personality traits | Adjusting bot tone |
| `AGENTS.md` | Operational instructions | Adding new capabilities |
| `memory/MEMORY.md` | Long-term memory | Never manually (agent maintains) |
| `TODOS.md` | Task list | Adding tasks for the agent |
| `HEARTBEAT.md` | Periodic self-check rules | Changing monitoring thresholds |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|------------|-----|
| No response in Telegram | Services down | `systemctl --user status openclaw-router openclaw-gateway` |
| Bot says "Taking longer than 300s" | LLM very slow or hanging | Try again; or restart router |
| Bot lists capabilities instead of answering | Router issue — check logs | `tail -20 /tmp/router_debug.log` |
| News requests get no web data | web_search.py broken | `python3 ~/.openclaw/workspace/skills/web-browser/scripts/web_search.py --query "test"` |
| Disk full (bot goes silent) | `.fbd*.so` file leak | `find /tmp -name '*.fbd*.so' -delete` |
| Can't SSH | Tailscale down or exit node issue | Use EC2 Instance Connect in AWS console |

---

## ⚠️ Critical Warning — Tailscale

**Never run `tailscale set --exit-node=...` on the VPS.** If the exit node goes offline, all routing breaks including SSH, and it persists through reboots.

**Recovery**: AWS EC2 console → Instance → Actions → Edit User Data → add:
```bash
#!/bin/bash
tailscale set --exit-node=
```
Stop and start (not reboot) the instance.

---

## Documentation

| File | Contents |
|------|---------|
| [HANDOVER.md](HANDOVER.md) | Full architecture, configuration, issue history |
| [SETUP.md](SETUP.md) | Step-by-step setup from scratch |
| [CLI_ROUTER.md](CLI_ROUTER.md) | Router v5 technical deep-dive |
| [TAILSCALE_SETUP.md](TAILSCALE_SETUP.md) | Network/VPN details |
| [VPS_SETUP_JOURNAL.md](VPS_SETUP_JOURNAL.md) | Chronological build history |

Last updated: 2026-02-23
