#!/bin/bash
# Expose the VC Agent Marketplace publicly via ngrok
#
# Usage:
#   bash bridges/setup_ngrok.sh
#
# Prerequisites:
#   1. Install ngrok: brew install ngrok  (or https://ngrok.com/download)
#   2. Sign up at ngrok.com and run: ngrok config add-authtoken YOUR_TOKEN
#   3. Start marketplace first: python run_server.py

set -e

PORT=${1:-8000}

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok is not installed."
    echo ""
    echo "Install it:"
    echo "  macOS:   brew install ngrok"
    echo "  Linux:   snap install ngrok"
    echo "  Manual:  https://ngrok.com/download"
    echo ""
    echo "Then authenticate:"
    echo "  ngrok config add-authtoken YOUR_TOKEN"
    echo "  (Get token at https://dashboard.ngrok.com/get-started/your-authtoken)"
    exit 1
fi

# Check if marketplace is running
if ! curl -s http://localhost:$PORT/api/agents > /dev/null 2>&1; then
    echo "⚠️  Marketplace doesn't seem to be running on port $PORT"
    echo "   Start it first: python run_server.py"
    echo ""
    echo "   Starting ngrok anyway..."
fi

echo "🚀 Starting ngrok tunnel on port $PORT..."
echo ""
echo "Once ngrok starts, use these URLs:"
echo ""
echo "  Dashboard:   https://xxx.ngrok.io/dashboard"
echo "  WebSocket:   wss://xxx.ngrok.io/ws/agent"
echo "  Hero page:   https://xxx.ngrok.io/"
echo ""
echo "For Telegram bridge:"
echo "  export MARKETPLACE_URL=wss://xxx.ngrok.io/ws/agent"
echo "  python bridges/telegram_bridge.py"
echo ""
echo "───────────────────────────────────────────"

ngrok http $PORT
