"""Base A2A agent — each agent is its own HTTP server with AgentCard + JSON-RPC endpoint."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from rich.console import Console

from a2a_marketplace.models.types import (
    AgentCard,
    Artifact,
    Capabilities,
    JsonRpcRequest,
    JsonRpcResponse,
    Message,
    Part,
    Skill,
    TaskResult,
    TaskStatus,
)

console = Console()


class BaseA2AAgent:
    """Base class for A2A-compliant agents. Subclasses implement handle_task()."""

    def __init__(self, profile: dict, agent_type: str, port: int, skills: list[dict]):
        self.profile = profile
        self.agent_type = agent_type
        self.port = port
        self.name = profile.get("name", "Agent")
        self.url = f"http://localhost:{port}"
        self.orchestrator_url = "http://localhost:8000"

        self.agent_card = AgentCard(
            name=self.name,
            description=self._build_description(),
            url=self.url,
            capabilities=Capabilities(),
            skills=[Skill(**s) for s in skills],
            metadata={"agent_type": agent_type, "profile": profile},
        )

        self.app = FastAPI(title=self.name)
        self._setup_routes()

    def _build_description(self) -> str:
        if self.agent_type == "startup":
            sector = self.profile.get("sector", "")
            stage = self.profile.get("stage", "")
            ask = self.profile.get("funding_ask", 0)
            return f"{self.name} — {sector} startup, {stage} stage, seeking ${ask:,}"
        else:
            firm = self.profile.get("firm_name", "")
            sectors = ", ".join(self.profile.get("target_sectors", []))
            return f"{self.name} — {firm}, investing in {sectors}"

    def _setup_routes(self):
        @self.app.get("/.well-known/agent.json")
        async def agent_card():
            return self.agent_card.model_dump()

        @self.app.post("/a2a")
        async def handle_jsonrpc(request: Request):
            body = await request.json()
            try:
                rpc = JsonRpcRequest(**body)
            except Exception as e:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": body.get("id", "unknown"),
                    "error": {"code": -32600, "message": f"Invalid request: {e}"},
                })

            if rpc.method == "tasks/send":
                try:
                    result = await self.handle_task(
                        task_id=rpc.params.id,
                        skill_id=rpc.params.skill_id or "",
                        message=rpc.params.message,
                    )
                    return JsonRpcResponse(
                        id=rpc.id,
                        result=result,
                    ).model_dump()
                except Exception as e:
                    console.print(f"[red]{self.name} task error: {e}[/red]")
                    return JsonRpcResponse(
                        id=rpc.id,
                        error={"code": -32000, "message": str(e)},
                    ).model_dump()
            else:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": rpc.id,
                    "error": {"code": -32601, "message": f"Method not found: {rpc.method}"},
                })

    async def handle_task(self, task_id: str, skill_id: str, message: Message) -> TaskResult:
        """Override in subclasses to handle specific skills."""
        return TaskResult(
            id=task_id,
            status=TaskStatus(state="failed"),
            artifacts=[Artifact(parts=[Part(type="text", text=f"Unknown skill: {skill_id}")])],
        )

    async def register_with_orchestrator(self):
        """Tell the orchestrator about this agent."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.orchestrator_url}/register-agent",
                    json={"url": self.url},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    console.print(f"[green]{self.name} registered with orchestrator[/green]")
                else:
                    console.print(f"[yellow]{self.name} registration failed: {resp.status_code}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]{self.name} registration error: {e}[/yellow]")

    def extract_text(self, message: Message) -> str:
        """Extract all text parts from a message."""
        return " ".join(p.text for p in message.parts if p.type == "text" and p.text)

    def extract_data(self, message: Message) -> dict:
        """Extract first data part from a message."""
        for p in message.parts:
            if p.type == "data" and p.data:
                return p.data
        return {}

    def make_response(self, task_id: str, text: str, data: dict | None = None) -> TaskResult:
        """Build a completed TaskResult with text and optional data."""
        parts = [Part(type="text", text=text)]
        if data:
            parts.append(Part(type="data", data=data))
        return TaskResult(
            id=task_id,
            status=TaskStatus(state="completed"),
            artifacts=[Artifact(parts=parts)],
        )

    async def run(self):
        """Start the HTTP server."""
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        console.print(f"[blue]{self.name}[/blue] A2A agent starting on port {self.port}")
        await server.serve()
