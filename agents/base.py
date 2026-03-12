import asyncio
import json

import websockets
from rich.console import Console

from agents.llm_client import think
from models.enums import AgentType, MessageType

console = Console()


class BaseAgent:
    """Base class for all agents (startup and VC).

    Each agent is fully autonomous:
    - Connects to the marketplace via WebSocket
    - Registers itself
    - Handles incoming messages independently
    - Reconnects automatically if disconnected
    """

    def __init__(self, agent_type: AgentType, profile: dict):
        self.agent_type = agent_type
        self.profile = profile
        self.name = profile.get("name") or profile.get("firm_name", "Unknown")
        self.agent_id: str | None = None
        self._ws = None
        self._running = False
        self._reconnect = True

    async def connect_and_run(self, marketplace_url: str = "ws://localhost:8000/ws/agent",
                              startup_delay: float = 0):
        """Connect to marketplace, register, and start message loop."""
        if startup_delay > 0:
            await asyncio.sleep(startup_delay)

        self._log("Connecting to marketplace...")

        try:
            async with websockets.connect(marketplace_url, ping_interval=20, ping_timeout=10) as ws:
                self._ws = ws
                self._running = True

                # Register
                await self._send({
                    "message_type": MessageType.REGISTER.value,
                    "sender_id": "pending",
                    "payload": {
                        "agent_type": self.agent_type.value,
                        "profile": self.profile,
                    },
                })

                # Wait for registration ack
                ack = await ws.recv()
                ack_data = json.loads(ack)
                if ack_data.get("message_type") == MessageType.REGISTER_ACK.value:
                    self.agent_id = ack_data["payload"]["agent_id"]
                    self._log(f"Registered as {self.agent_id}")

                # Post-registration hook (autonomous behavior starts here)
                await self.on_registered()

                # Message loop - agent listens and responds autonomously
                async for raw in ws:
                    data = json.loads(raw)
                    msg_type = data.get("message_type")
                    if msg_type == "heartbeat":
                        continue
                    await self.handle_message(data)

        except websockets.exceptions.ConnectionClosed:
            self._log("Disconnected from marketplace")
        except ConnectionRefusedError:
            self._log("Marketplace not available")
        except Exception as e:
            self._log(f"Error: {e}")
        finally:
            self._running = False
            self._ws = None

    async def on_registered(self):
        """Called after successful registration. Override in subclasses for autonomous behavior."""
        pass

    async def handle_message(self, data: dict):
        """Dispatch incoming messages. Override in subclasses."""
        pass

    async def _send(self, data: dict):
        """Send a JSON message to the marketplace."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def send_message(self, message_type: MessageType, payload: dict,
                           recipient_id: str | None = None):
        """Send a typed message through the marketplace."""
        await self._send({
            "message_type": message_type.value,
            "sender_id": self.agent_id or "pending",
            "recipient_id": recipient_id,
            "payload": payload,
        })

    async def llm_think(self, system_prompt: str, user_prompt: str) -> str:
        """Use the LLM to generate a response."""
        return await think(system_prompt, user_prompt)

    def _log(self, message: str):
        type_label = "STARTUP" if self.agent_type == AgentType.STARTUP else "VC"
        style = "green" if self.agent_type == AgentType.STARTUP else "cyan"
        console.print(f"[{style}]{type_label:<8} {self.name}[/{style}]  {message}")
