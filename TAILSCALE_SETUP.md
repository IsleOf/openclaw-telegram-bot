# Tailscale Network Setup

## Network Nodes

| Device | Tailscale IP | Notes |
|--------|-------------|-------|
| AWS VPS | 100.93.10.110 | Main server |
| Dev machine | 100.88.215.17 | Local development |
| Android TV stick | 100.70.48.72 | Exit node (unreliable) |
| Other exit node | 100.126.193.35 | Alternative exit node |

## SSH Access

```bash
ssh ubuntu@100.93.10.110
```

Uses ed25519 key at `/home/dev/.ssh/id_ed25519`.

## Critical Warning

**Do NOT set a Tailscale exit node on the VPS.** Running `tailscale set --exit-node=...` routes ALL VPS traffic through the exit node. If that node goes offline, the VPS becomes unreachable — even SSH breaks, and it persists across reboots.

If this happens, fix via AWS EC2 console:
1. Stop the instance
2. Edit user data, add: `#!/bin/bash\ntailscale set --exit-node=`
3. Start the instance
4. Re-add SSH key if needed

## Exit Nodes for Web Browsing

The web browser skill on the VPS may need an exit node to avoid IP-based blocking. Use exit nodes only for the browser scripts, not system-wide. The `ddgs` Python library works without exit nodes for search.

## Tailscale Commands

```bash
# Check status
tailscale status

# Check if exit node is set (should be empty on VPS)
tailscale status --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('ExitNodeStatus', 'none'))"
```

Last updated: 2026-02-20
