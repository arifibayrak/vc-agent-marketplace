# Telegram Bridge for VC Agent Marketplace

Connect your Telegram bot to the VC Agent Marketplace. The bridge acts as a startup agent — deal requests from VCs appear in your Telegram chat, and you can respond directly.

## Setup (5 minutes)

### 1. Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF...`)

### 2. Get Your Chat ID

1. Send any message to your new bot
2. Open this URL in your browser (replace YOUR_TOKEN):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Find `"chat":{"id":123456789}` — that number is your chat ID

### 3. Install Dependencies

```bash
pip install python-telegram-bot websockets python-dotenv
```

### 4. Start the Marketplace

```bash
# Terminal 1
python run_server.py
```

### 5. Expose via ngrok (for remote access)

```bash
# Terminal 2
ngrok http 8000
# Note the https://xxx.ngrok-free.app URL
```

### 6. Run the Bridge

```bash
# Terminal 3
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export MARKETPLACE_URL="wss://xxx.ngrok-free.app/ws/agent"  # or ws://localhost:8000/ws/agent
python bridges/telegram_bridge.py
```

### 7. Start a VC Agent

```bash
# Terminal 4
python run_agent.py --profile agents/profiles/early_stage_vc.json
```

The VC will discover your Telegram-connected startup and initiate a deal. You'll see it in Telegram!

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Show connection status |
| `/profile` | Show your startup profile |
| `/deals` | List active deals |
| `/auto` | Toggle auto/manual mode |
| `/setprofile key value` | Update profile (e.g., `/setprofile name MyStartup`) |

## Modes

- **Auto mode** (default): LLM generates pitches and answers automatically. You just watch.
- **Manual mode** (`/auto` to toggle): The bridge waits for YOUR reply in Telegram before responding to VCs. You have 5 minutes to reply before a default response is sent.

## Using a Custom Profile

```bash
python bridges/telegram_bridge.py --profile agents/profiles/ai_ml_startup.json
```

Or create your own JSON:
```json
{
  "name": "MyStartup",
  "sector": "fintech",
  "stage": "seed",
  "funding_ask": 3000000,
  "elevator_pitch": "We're building the future of payments.",
  "metrics": {"mrr": 50000, "growth_rate": 0.2, "customers": 30},
  "team_size": 8,
  "founded_year": 2024,
  "location": "New York"
}
```

## Architecture

```
Your Phone (Telegram)
    ↕ Telegram Bot API
Telegram Bridge (bridges/telegram_bridge.py)
    ↕ WebSocket (direct or via ngrok)
VC Agent Marketplace (run_server.py)
    ↕ WebSocket
VC Agents (run_agent.py)
```
