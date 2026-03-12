#!/usr/bin/env python3
"""Minimal example: connect an external startup agent to the marketplace.

Usage:
    pip install websockets
    python run_server.py        # in one terminal
    python examples/python_client.py  # in another terminal
"""

import asyncio
import json
import websockets


MARKETPLACE_URL = "ws://localhost:8000/ws/agent"

PROFILE = {
    "name": "MyExternalBot",
    "sector": "ai_ml",
    "stage": "seed",
    "funding_ask": 2000000,
    "elevator_pitch": "We build autonomous coding agents that ship production code.",
    "metrics": {"mrr": 30000, "growth_rate": 0.25, "customers": 8},
    "team_size": 5,
    "founded_year": 2025,
    "location": "Remote",
}


async def main():
    async with websockets.connect(MARKETPLACE_URL) as ws:
        # 1. Register
        await ws.send(json.dumps({
            "message_type": "register",
            "sender_id": "pending",
            "payload": {"agent_type": "startup", "profile": PROFILE},
        }))

        ack = json.loads(await ws.recv())
        agent_id = ack["payload"]["agent_id"]
        print(f"Registered as: {agent_id}")

        # 2. Listen and respond
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("message_type")
            payload = msg.get("payload", {})

            if msg_type == "deal_initiated":
                deal_id = payload["deal_id"]
                vc_name = payload.get("vc_profile", {}).get("name", "A VC")
                print(f"Deal from {vc_name} ({deal_id})")

                # Send pitch
                await ws.send(json.dumps({
                    "message_type": "pitch",
                    "sender_id": agent_id,
                    "payload": {
                        "deal_id": deal_id,
                        "elevator_pitch": PROFILE["elevator_pitch"],
                        "key_metrics": PROFILE["metrics"],
                        "funding_ask": PROFILE["funding_ask"],
                        "use_of_funds": "Engineering and go-to-market",
                        "competitive_advantage": "Best-in-class AI code generation",
                    },
                }))
                print(f"  Sent pitch for {deal_id}")

            elif msg_type == "question":
                deal_id = payload["deal_id"]
                questions = payload.get("questions", [])
                print(f"Got {len(questions)} questions for {deal_id}")

                answers = [
                    {"question": q, "answer": f"Great question about '{q}'. Here's our data..."}
                    for q in questions
                ]
                await ws.send(json.dumps({
                    "message_type": "answer",
                    "sender_id": agent_id,
                    "payload": {"deal_id": deal_id, "answers": answers},
                }))
                print(f"  Sent answers for {deal_id}")

            elif msg_type == "deal_update":
                status = payload.get("status")
                message = payload.get("message", "")
                print(f"Decision: {status} - {message[:100]}")

            elif msg_type == "heartbeat":
                pass  # keepalive ack

            else:
                print(f"Unknown message: {msg_type}")


if __name__ == "__main__":
    asyncio.run(main())
