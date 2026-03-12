#!/usr/bin/env python3
"""
Telegram Bridge — Connect any Telegram bot/chat to the VC Agent Marketplace.

This bridge acts as a startup agent that:
1. Connects to the marketplace via WebSocket
2. Forwards deal messages to your Telegram chat
3. Sends your Telegram replies back to the marketplace

Usage:
    export TELEGRAM_BOT_TOKEN="your-bot-token-from-botfather"
    export TELEGRAM_CHAT_ID="your-chat-id"
    export MARKETPLACE_URL="ws://localhost:8000/ws/agent"  # or wss://xxx.ngrok.io/ws/agent
    python bridges/telegram_bridge.py

    # Or with a custom profile:
    python bridges/telegram_bridge.py --profile agents/profiles/ai_ml_startup.json

Get your chat ID: send any message to your bot, then visit:
    https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import websockets
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    format="%(asctime)s [BRIDGE] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MARKETPLACE_URL = os.getenv("MARKETPLACE_URL", "ws://localhost:8000/ws/agent")

DEFAULT_PROFILE = {
    "name": "TelegramAgent",
    "sector": "ai_ml",
    "stage": "seed",
    "funding_ask": 2000000,
    "elevator_pitch": "An AI-powered startup connected via Telegram bridge.",
    "metrics": {"mrr": 25000, "growth_rate": 0.20, "customers": 10},
    "team_size": 5,
    "founded_year": 2025,
    "location": "Remote",
}

# ─── Bridge State ─────────────────────────────────────────────────────────────


class BridgeState:
    def __init__(self):
        self.agent_id: str | None = None
        self.ws = None
        self.profile: dict = DEFAULT_PROFILE.copy()
        self.auto_mode: bool = True  # LLM answers automatically by default
        self.active_deals: dict[str, dict] = {}  # deal_id -> deal info
        self.pending_replies: dict[str, asyncio.Future] = {}  # deal_id -> Future
        self.bot: Bot | None = None
        self.connected: bool = False


state = BridgeState()

# ─── Telegram Handlers ───────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "Connected" if state.connected else "Disconnected"
    agent = state.agent_id or "Not registered"
    mode = "Auto (LLM)" if state.auto_mode else "Manual (you reply)"
    await update.message.reply_text(
        f"🤖 *VC Marketplace Telegram Bridge*\n\n"
        f"*Status:* {status}\n"
        f"*Agent ID:* `{agent}`\n"
        f"*Marketplace:* `{MARKETPLACE_URL}`\n"
        f"*Mode:* {mode}\n"
        f"*Active deals:* {len(state.active_deals)}\n\n"
        f"*Commands:*\n"
        f"/profile — Show startup profile\n"
        f"/deals — Show active deals\n"
        f"/auto — Toggle auto/manual mode\n"
        f"/setprofile — Update profile fields",
        parse_mode="Markdown",
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = state.profile
    await update.message.reply_text(
        f"📋 *Startup Profile*\n\n"
        f"*Name:* {p['name']}\n"
        f"*Sector:* {p['sector']}\n"
        f"*Stage:* {p['stage']}\n"
        f"*Funding Ask:* ${p['funding_ask']:,}\n"
        f"*Pitch:* {p['elevator_pitch']}\n"
        f"*MRR:* ${p.get('metrics', {}).get('mrr', 0):,}\n"
        f"*Customers:* {p.get('metrics', {}).get('customers', 0)}\n"
        f"*Team:* {p.get('team_size', 0)} people\n"
        f"*Location:* {p.get('location', 'N/A')}",
        parse_mode="Markdown",
    )


async def cmd_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state.active_deals:
        await update.message.reply_text("No active deals.")
        return
    lines = []
    for deal_id, info in state.active_deals.items():
        vc = info.get("vc_name", "Unknown VC")
        status = info.get("status", "active")
        lines.append(f"• `{deal_id[:12]}...` with *{vc}* — {status}")
    await update.message.reply_text(
        f"📊 *Active Deals ({len(state.active_deals)})*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state.auto_mode = not state.auto_mode
    mode = "AUTO (LLM responds)" if state.auto_mode else "MANUAL (you type replies)"
    await update.message.reply_text(f"🔄 Mode switched to: *{mode}*", parse_mode="Markdown")


async def cmd_setprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/setprofile key value`\n"
            "Example: `/setprofile name MyStartup`\n"
            "Valid keys: name, sector, stage, funding_ask, elevator_pitch, location, team_size",
            parse_mode="Markdown",
        )
        return
    key = context.args[0]
    value = " ".join(context.args[1:])
    if key in ("funding_ask", "team_size"):
        value = int(value)
    if key in state.profile:
        state.profile[key] = value
        await update.message.reply_text(f"Updated *{key}* = `{value}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Unknown key: {key}")


async def handle_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text replies from the user — resolve pending deal replies."""
    text = update.message.text

    # Check if there's a pending reply (FIFO — resolve the oldest one)
    if state.pending_replies:
        deal_id = next(iter(state.pending_replies))
        future = state.pending_replies.pop(deal_id)
        if not future.done():
            future.set_result(text)
            await update.message.reply_text(
                f"✅ Reply sent for deal `{deal_id[:12]}...`", parse_mode="Markdown"
            )
            return

    await update.message.reply_text(
        "No pending deal to reply to. Your message was not sent to the marketplace."
    )


# ─── Telegram → Marketplace (send helpers) ───────────────────────────────────


async def send_to_telegram(text: str):
    """Send a message to the configured Telegram chat."""
    if state.bot and TELEGRAM_CHAT_ID:
        try:
            await state.bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID), text=text, parse_mode="Markdown"
            )
        except Exception as e:
            log.error(f"Telegram send error: {e}")


# ─── WebSocket → Telegram (marketplace message handlers) ─────────────────────


async def handle_deal_initiated(payload: dict):
    """VC wants to connect. Forward to Telegram, auto-pitch or wait for reply."""
    deal_id = payload.get("deal_id", "unknown")
    vc_profile = payload.get("vc_profile", {})
    vc_name = vc_profile.get("name") or vc_profile.get("firm_name", "Unknown VC")
    intro = payload.get("intro_message", "")

    state.active_deals[deal_id] = {
        "vc_name": vc_name,
        "vc_profile": vc_profile,
        "status": "initiated",
    }

    await send_to_telegram(
        f"🚀 *New Deal from {vc_name}!*\n\n"
        f"*Firm:* {vc_profile.get('firm_name', 'N/A')}\n"
        f"*Focus:* {vc_profile.get('portfolio_focus', 'N/A')}\n"
        f"*Check size:* ${vc_profile.get('check_size_min', 0):,} - ${vc_profile.get('check_size_max', 0):,}\n"
        f"*Message:* {intro}\n\n"
        f"{'🤖 Auto-pitching...' if state.auto_mode else '✏️ Type your pitch and send it!'}"
    )

    if state.auto_mode:
        # Auto-generate pitch
        pitch_text = state.profile["elevator_pitch"]
        try:
            from agents.llm_client import think, _fallback_mode

            if not _fallback_mode:
                system = (
                    f"You are {state.profile['name']}, a startup founder. "
                    f"Company: {state.profile['elevator_pitch']}. "
                    f"Sector: {state.profile['sector']}. Stage: {state.profile['stage']}."
                )
                pitch_text = await think(
                    system,
                    f"A VC ({vc_name}) from {vc_profile.get('firm_name', '')} reached out. "
                    f"Their focus: {vc_profile.get('portfolio_focus', '')}. "
                    "Generate a compelling 3-4 sentence pitch.",
                )
        except Exception:
            pass

        await _send_pitch(deal_id, pitch_text)
        await send_to_telegram(f"✅ Auto-pitch sent for deal with *{vc_name}*")
    else:
        # Wait for user reply
        future = asyncio.get_event_loop().create_future()
        state.pending_replies[deal_id] = future
        try:
            pitch_text = await asyncio.wait_for(future, timeout=300)
            await _send_pitch(deal_id, pitch_text)
        except asyncio.TimeoutError:
            state.pending_replies.pop(deal_id, None)
            await _send_pitch(deal_id, state.profile["elevator_pitch"])
            await send_to_telegram(f"⏰ Timeout — sent default pitch for *{vc_name}*")


async def handle_questions(payload: dict):
    """VC asks due diligence questions. Forward to Telegram."""
    deal_id = payload.get("deal_id", "unknown")
    questions = payload.get("questions", [])
    sender = payload.get("sender_id", "")

    if deal_id in state.active_deals:
        state.active_deals[deal_id]["status"] = "in_diligence"

    q_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    await send_to_telegram(
        f"❓ *Due Diligence Questions* (deal `{deal_id[:12]}...`)\n\n{q_text}\n\n"
        f"{'🤖 Auto-answering...' if state.auto_mode else '✏️ Type your answers and send!'}"
    )

    if state.auto_mode:
        answers = []
        for q in questions:
            try:
                from agents.llm_client import think, _fallback_mode

                if not _fallback_mode:
                    system = (
                        f"You are {state.profile['name']}. "
                        f"Metrics: {json.dumps(state.profile.get('metrics', {}))}."
                    )
                    a = await think(system, f"VC asks: \"{q}\". Answer in 2-3 sentences.")
                else:
                    a = f"Regarding '{q}': we have strong fundamentals in this area."
            except Exception:
                a = f"Regarding '{q}': we have strong fundamentals in this area."
            answers.append({"question": q, "answer": a})

        await _send_answers(deal_id, answers)
        await send_to_telegram(f"✅ Auto-answered {len(questions)} questions")
    else:
        future = asyncio.get_event_loop().create_future()
        state.pending_replies[deal_id] = future
        try:
            reply_text = await asyncio.wait_for(future, timeout=300)
            answers = [{"question": q, "answer": reply_text} for q in questions]
            await _send_answers(deal_id, answers)
        except asyncio.TimeoutError:
            state.pending_replies.pop(deal_id, None)
            answers = [
                {"question": q, "answer": "We will follow up with details shortly."}
                for q in questions
            ]
            await _send_answers(deal_id, answers)
            await send_to_telegram("⏰ Timeout — sent default answers")


async def handle_deal_update(payload: dict):
    """VC made a decision. Notify via Telegram."""
    deal_id = payload.get("deal_id", "unknown")
    status = payload.get("status", "")
    message = payload.get("message", "")
    next_steps = payload.get("next_steps", "")

    if deal_id in state.active_deals:
        state.active_deals[deal_id]["status"] = status

    if status == "interest":
        emoji = "🎉"
        title = "VC IS INTERESTED!"
    elif status == "passed":
        emoji = "😔"
        title = "VC PASSED"
    else:
        emoji = "📢"
        title = f"Deal Update: {status}"

    text = f"{emoji} *{title}*\n\nDeal: `{deal_id[:12]}...`\n*Reasoning:* {message[:500]}"
    if next_steps:
        text += f"\n*Next steps:* {next_steps}"

    await send_to_telegram(text)


# ─── WebSocket Send Helpers ───────────────────────────────────────────────────


async def _send_pitch(deal_id: str, pitch_text: str):
    if state.ws:
        await state.ws.send(
            json.dumps(
                {
                    "message_type": "pitch",
                    "sender_id": state.agent_id,
                    "payload": {
                        "deal_id": deal_id,
                        "elevator_pitch": pitch_text,
                        "key_metrics": state.profile.get("metrics", {}),
                        "funding_ask": state.profile.get("funding_ask", 0),
                        "use_of_funds": "Product development and growth",
                        "competitive_advantage": f"Leading innovation in {state.profile.get('sector', 'tech')}",
                    },
                }
            )
        )


async def _send_answers(deal_id: str, answers: list):
    if state.ws:
        await state.ws.send(
            json.dumps(
                {
                    "message_type": "answer",
                    "sender_id": state.agent_id,
                    "payload": {"deal_id": deal_id, "answers": answers},
                }
            )
        )


# ─── WebSocket Connection Loop ───────────────────────────────────────────────


async def websocket_loop():
    """Connect to marketplace, register, and handle messages."""
    while True:
        try:
            log.info(f"Connecting to {MARKETPLACE_URL}...")
            async with websockets.connect(
                MARKETPLACE_URL, ping_interval=20, ping_timeout=10
            ) as ws:
                state.ws = ws
                state.connected = True

                # Register
                await ws.send(
                    json.dumps(
                        {
                            "message_type": "register",
                            "sender_id": "pending",
                            "payload": {
                                "agent_type": "startup",
                                "profile": state.profile,
                            },
                        }
                    )
                )

                # Wait for ack
                ack = json.loads(await ws.recv())
                if ack.get("message_type") == "register_ack":
                    state.agent_id = ack["payload"]["agent_id"]
                    log.info(f"Registered as {state.agent_id}")
                    await send_to_telegram(
                        f"✅ *Connected to marketplace!*\n"
                        f"Agent ID: `{state.agent_id}`\n"
                        f"Profile: *{state.profile['name']}*"
                    )

                # Message loop
                async for raw in ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("message_type")
                    payload = msg.get("payload", {})

                    if msg_type == "deal_initiated":
                        asyncio.create_task(handle_deal_initiated(payload))
                    elif msg_type == "question":
                        asyncio.create_task(handle_questions(payload))
                    elif msg_type == "deal_update":
                        asyncio.create_task(handle_deal_update(payload))
                    elif msg_type == "heartbeat":
                        pass
                    else:
                        log.info(f"Unknown message: {msg_type}")

        except websockets.exceptions.ConnectionClosed:
            log.warning("Disconnected from marketplace")
        except ConnectionRefusedError:
            log.warning("Marketplace not available")
        except Exception as e:
            log.error(f"WebSocket error: {e}")
        finally:
            state.connected = False
            state.ws = None

        log.info("Reconnecting in 5 seconds...")
        await send_to_telegram("⚠️ Disconnected from marketplace. Reconnecting...")
        await asyncio.sleep(5)


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN environment variable")
        print("  1. Talk to @BotFather on Telegram")
        print("  2. Create a bot with /newbot")
        print("  3. Copy the token")
        print("  4. export TELEGRAM_BOT_TOKEN='your-token'")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        print("ERROR: Set TELEGRAM_CHAT_ID environment variable")
        print("  1. Send any message to your bot on Telegram")
        print(f"  2. Visit: https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates")
        print("  3. Find your chat.id in the response")
        print("  4. export TELEGRAM_CHAT_ID='your-chat-id'")
        sys.exit(1)

    # Try to init LLM for auto-mode
    try:
        from agents.llm_client import init_llm
        init_llm()
    except Exception:
        log.info("LLM not available — auto-mode will use simple responses")

    # Build Telegram bot
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("deals", cmd_deals))
    app.add_handler(CommandHandler("auto", cmd_auto))
    app.add_handler(CommandHandler("setprofile", cmd_setprofile))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_reply))

    state.bot = app.bot

    log.info(f"Starting Telegram bridge...")
    log.info(f"  Marketplace: {MARKETPLACE_URL}")
    log.info(f"  Chat ID: {TELEGRAM_CHAT_ID}")
    log.info(f"  Profile: {state.profile['name']}")

    # Run both Telegram bot and WebSocket loop concurrently
    async with app:
        await app.start()
        await app.updater.start_polling()

        try:
            await websocket_loop()
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram Bridge for VC Marketplace")
    parser.add_argument("--profile", help="Path to startup profile JSON file")
    parser.add_argument("--url", default=None, help="Marketplace WebSocket URL")
    args = parser.parse_args()

    if args.profile:
        with open(args.profile) as f:
            state.profile = json.load(f)
        log.info(f"Loaded profile from {args.profile}")

    if args.url:
        MARKETPLACE_URL = args.url

    asyncio.run(main())
