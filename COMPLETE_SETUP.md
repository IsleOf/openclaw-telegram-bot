# OpenClaw AWS Server - Complete Setup

## Connection Info

| Item | Value |
|------|-------|
| **OpenCode Tailscale IP** | `100.88.215.17` |
| **AWS Server Tailscale IP** | `100.93.10.110` |
| **AWS Public IP** | `3.106.138.96` |
| **SSH Key** | `/home/dev/.ssh/tailscale_key` |
| **OpenClaw Port** | `18789` |

---

## Quick Connect (For Future Agents)

### 1. Connect to AWS via Tailscale:
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

### 2. Access OpenClaw Gateway (via SSH tunnel):
```bash
# Create tunnel
ssh -i ~/.ssh/tailscale_key -L 18789:127.0.0.1:18789 -N -f ubuntu@100.93.10.110

# Access in browser
curl http://127.0.0.1:18789/
```

### 3. Or run commands directly:
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110 'export PATH=$HOME/.npm-global/bin:$PATH && openclaw gateway status'
```

---

## OpenClaw Status

- **Status**: ✅ Running
- **Current Model**: Kimi K2.5 (via OpenRouter)
- **Available Models**: OpenRouter Auto, Claude 3.5 Sonnet, Claude 3 Opus, Gemini Pro, Gemini Flash, Kimi K2.5
- **Channel**: Telegram enabled

---

## Available Commands

```bash
# Check status
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110 'export PATH=$HOME/.npm-global/bin:$PATH && openclaw gateway status'

# Restart gateway
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110 'export PATH=$HOME/.npm-global/bin:$PATH && openclaw gateway restart'

# List models
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110 'export PATH=$HOME/.npm-global/bin:$PATH && openclaw models list'

# View logs
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110 'tail -f /tmp/openclaw/openclaw-2026-02-15.log'
```

---

## Setup Details

### SSH Key for Tailscale Access
- **Public Key**: `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDtkUZLTUsJbVtHgHo3Wi3Wrw7lrgwt0qapuW9aoL/Oz dev@DESKTOP-F3V5NK7`
- **Private Key**: `/home/dev/.ssh/tailscale_key`

### Tailscale Status
- ✅ Both machines connected to same Tailscale network
- SSH keys exchanged for passwordless access

---

## Adding New Models

Edit `/home/ubuntu/.openclaw/openclaw.json` and add models under `agents.defaults.models`, then restart gateway.

---

## Last Updated
2026-02-15

## Notes
- Gateway is bound to loopback (127.0.0.1) for security
- Access via SSH tunnel from Tailscale
- Telegram bot token: `8573345722:AAFU5BUISq4j7HOAI2x7NvblVDRtVC30Vyc`
- Gateway token: `4272baca0ae5b42729b6db36a633745511a0cdfa9e9db8b6`
