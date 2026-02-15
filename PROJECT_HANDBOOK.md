# OpenClaw AWS Server - Project Documentation

## Server Information

- **Server IP**: 3.106.138.96 (Public)
- **Instance**: ip-172-31-36-81.ap-southeast-2.compute.internal
- **SSH Key**: `C:\Users\PC\Downloads\openclaw_serverr.pem`
- **SSH User**: ubuntu

## Access Methods

### Method 1: Command Server (Autonomous Agent Access)
```bash
# Start the command server on the AWS server:
cd ~/cmd-server && node server.js &

# Then expose via bore:
bore local 7777 --to bore.pub

# Agent uses: http://bore.pub:PORT/exec
```

### Method 2: Direct SSH
```bash
ssh -i "C:\Users\PC\Downloads\openclaw_serverr.pem" ubuntu@3.106.138.96
```

## Installed Components

- OpenClaw 2026.2.13
- Node.js 20.x
- Telegram Bot (enabled)
- Command Server (port 7777)

## Configuration

Config file: `~/.openclaw/openclaw.json`

### Available Models (OpenRouter)
- OpenRouter Auto
- Claude 3.5 Sonnet
- Claude 3 Opus
- Gemini Pro
- Gemini Flash
- Llama 3.1 405B
- Kimi K2.5
- Qwen 2.5 72B
- DeepSeek Chat

## Quick Commands

```bash
# Check status
openclaw gateway status

# Restart
openclaw gateway restart

# List models
openclaw models list

# View logs
tail -f /tmp/openclaw/openclaw-2026-02-15.log
```

## Agent Setup Script

To give an AI agent autonomous access:

1. Run on server:
```bash
# Install node if needed
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Create command server
mkdir -p ~/cmd-server
cd ~/cmd-server
npm init -y
npm install express ws

# Create server.js (see below)
cat > ~/cmd-server/server.js << 'EOF'
const express = require('express');
const { spawn } = require('child_process');
const app = express();
app.use(express.json());
app.post('/exec', (req, res) => {
  const cmd = req.body.command;
  if (!cmd) return res.json({error: 'No command'});
  const shell = spawn(cmd, [], {shell: true, cwd: process.env.HOME || '/home/ubuntu'});
  let output = '';
  shell.stdout.on('data', d => output += d);
  shell.stderr.on('data', d => output += d);
  shell.on('close', code => res.json({output, code}));
  setTimeout(() => {shell.kill(); res.json({output, code: -1, timeout: true})}, 30000);
});
app.listen(7777, '0.0.0.0', () => console.log('CMD_SERVER_READY'));
EOF

# Start server
node ~/cmd-server/server.js &

# Expose via bore (gets public URL)
bore local 7777 --to bore.pub
```

2. Agent connects via:
```bash
curl -X POST http://bore.pub:PORT/exec -H "Content-Type: application/json" -d '{"command": "YOUR_COMMAND"}'
```

## Future Agent Commands

The agent can use these commands to manage the server:

```bash
# Fix config issues
openclaw doctor --fix

# Check gateway
openclaw gateway status

# View logs
openclaw logs

# Add new models via OpenRouter
# Edit ~/.openclaw/openclaw.json and add model entries

# Restart after config changes
openclaw gateway restart
```

## Security Notes

- Keep the bore tunnel URL private
- The command server has full shell access - use carefully
- Telegram bot token is stored in config
- Gateway token: `4272baca0ae5b42729b6db36a633745511a0cdfa9e9db8b6`

## Troubleshooting

```bash
# Server not responding?
ps aux | grep node
kill -9 PID && cd ~/cmd-server && node server.js &

# Bore tunnel down?
bore local 7777 --to bore.pub

# OpenClaw issues?
openclaw doctor --fix
openclaw gateway restart
```
