import json
from dataclasses import dataclass, field

from fastapi import WebSocket

from marketplace import database, event_bus
from models.enums import AgentType


@dataclass
class ConnectedAgent:
    agent_id: str
    agent_type: AgentType
    name: str
    profile: dict
    websocket: WebSocket


class AgentRegistry:
    """Manages connected agents and their WebSocket connections."""

    def __init__(self):
        self._agents: dict[str, ConnectedAgent] = {}

    async def register(self, agent_id: str, agent_type: AgentType, name: str,
                       profile: dict, websocket: WebSocket) -> ConnectedAgent:
        agent = ConnectedAgent(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name,
            profile=profile,
            websocket=websocket,
        )
        self._agents[agent_id] = agent

        # Persist to database
        await database.save_agent(agent_id, agent_type.value, name, profile)

        type_label = "STARTUP" if agent_type == AgentType.STARTUP else "VC"
        sector = profile.get("sector", profile.get("target_sectors", [""])[0] if isinstance(profile.get("target_sectors"), list) else "")
        stage = profile.get("stage", "")
        await event_bus.emit_marketplace_event(
            f"Agent registered: {name} ({agent_type.value}/{sector}/{stage})",
            agent_id=agent_id,
        )
        return agent

    async def unregister(self, agent_id: str):
        if agent_id in self._agents:
            name = self._agents[agent_id].name
            del self._agents[agent_id]
            await event_bus.emit_marketplace_event(f"Agent disconnected: {name}", agent_id=agent_id)

    def get(self, agent_id: str) -> ConnectedAgent | None:
        return self._agents.get(agent_id)

    def get_all(self) -> list[ConnectedAgent]:
        return list(self._agents.values())

    def get_by_type(self, agent_type: AgentType) -> list[ConnectedAgent]:
        return [a for a in self._agents.values() if a.agent_type == agent_type]

    def get_startups(self) -> list[ConnectedAgent]:
        return self.get_by_type(AgentType.STARTUP)

    def get_vcs(self) -> list[ConnectedAgent]:
        return self.get_by_type(AgentType.VC)

    async def send_to(self, agent_id: str, data: dict) -> bool:
        """Send a JSON message to a specific agent via their WebSocket."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        try:
            await agent.websocket.send_json(data)
            return True
        except Exception:
            await self.unregister(agent_id)
            return False
