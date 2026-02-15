# OpenClaw AWS Server - Tailscale Setup

## Connection Info

- **OpenCode Tailscale IP**: 100.88.215.17
- **AWS Server Tailscale IP**: 100.93.10.110
- **AWS Public IP**: 3.106.138.96
- **SSH Key**: `C:\Users\PC\Downloads\openclaw_serverr.pem`

## Quick Connect Commands

### From OpenCode to AWS Server:
```bash
ssh -i ~/.ssh/tailscale_key ubuntu@100.93.10.110
```

Or use the SSH key stored at: `/home/dev/.ssh/tailscale_key`

### Copy key to server (first time):
```bash
ssh-copy-id -i ~/.ssh/tailscale_key.pub ubuntu@100.93.10.110
```

Or manually add this public key to AWS server's `~/.ssh/authorized_keys`:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDtkUZLTUsJbVtHgHo3Wi3Wrw7lrgwt0qapuW9aoL/Oz dev@DESKTOP-F3V5NK7
```

### Access OpenClaw Gateway:
```bash
curl http://100.93.10.110:18789/
```

## Tailscale Setup (Already Done)

### On this machine (OpenCode):
```bash
# Install Tailscale
echo " " | sudo -S sh -c 'curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg > /dev/null && curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list > /dev/null && apt-get update && apt-get install -y tailscale'

# Connect to Tailscale
echo " " | sudo -S tailscale up

# Get Tailscale IP
tailscale ip -4
```

### On AWS Server (already connected):
```bash
# Already has Tailscale installed and running
tailscale ip -4
```

## For Future Agents

When another agent needs to connect:

1. **Install Tailscale** on the agent's machine (see commands above)
2. **Authenticate** via the URL provided by `tailscale up`
3. **SSH** to AWS server: `ssh ubuntu@100.93.10.110`

## Troubleshooting

```bash
# Check Tailscale status on OpenCode
tailscale status

# Check Tailscale status on AWS
ssh ubuntu@100.93.10.110 'tailscale status'

# Restart Tailscale on AWS
ssh ubuntu@100.93.10.110 'sudo tailscale down && sudo tailscale up'
```

## OpenClaw Commands

```bash
# On AWS server
ssh ubuntu@100.93.10.110 'openclaw gateway status'
ssh ubuntu@100.93.10.110 'openclaw gateway restart'
ssh ubuntu@100.93.10.110 'openclaw models list'
ssh ubuntu@100.93.10.110 'openclaw doctor --fix'
```

## Last Updated
2026-02-15
