#!/bin/bash
# OpenClaw Auto-Setup Script
# Run: curl -sSL YOUR_SERVER_URL/openclaw-setup.sh | bash

set -e

echo "🦞 OpenClaw Auto-Setup Starting..."

# Get the directory where this script is running from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If no args provided, download files
if [ $# -eq 0 ]; then
    echo "📥 Downloading configuration files..."
    
    # Download openclaw.json
    echo "Downloading openclaw.json..."
    curl -sSL "https://raw.githubusercontent.com/"${GITHUB_USER:-"user"}/${GITHUB_REPO:-"repo"}/main/openclaw.json -o ~/.openclaw/openclaw.json 2>/dev/null || \
    curl -sSL "http://$(curl -s ifconfig.me):8000/openclaw.json" -o ~/.openclaw/openclaw.json 2>/dev/null || \
    echo "⚠️ Could not auto-download, will use local config"
    
    # Try to get from localhost:8000 if server is running
    echo "📡 Checking for local server..."
    curl -s localhost:8000/openclaw.json -o ~/.openclaw/openclaw.json 2>/dev/null && echo "✅ Downloaded from local server" || true
fi

# Backup existing config
if [ -f ~/.openclaw/openclaw.json ]; then
    echo "📦 Backing up existing config..."
    cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup.$(date +%s)
fi

# Apply local config if it exists in script directory
if [ -f "$SCRIPT_DIR/openclaw.json" ]; then
    echo "📄 Using local config from $SCRIPT_DIR"
    cp "$SCRIPT_DIR/openclaw.json" ~/.openclaw/openclaw.json
fi

# Fix config
echo "🔧 Running OpenClaw doctor..."
openclaw doctor --fix 2>/dev/null || true

# Restart gateway
echo "🔄 Restarting OpenClaw gateway..."
openclaw gateway restart

# Wait for startup
sleep 3

# Check status
echo ""
echo "📊 OpenClaw Status:"
openclaw gateway status 2>&1 | head -30

echo ""
echo "🎉 Setup Complete!"
echo ""
echo "Available models:"
openclaw models list 2>&1 | head -20 || true
