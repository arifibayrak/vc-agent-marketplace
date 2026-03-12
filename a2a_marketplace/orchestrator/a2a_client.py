"""A2A protocol HTTP client — sends tasks to agent servers."""

from __future__ import annotations

from uuid import uuid4

import httpx
from rich.console import Console

from a2a_marketplace.models.types import (
    AgentCard,
    Artifact,
    JsonRpcResponse,
    Message,
    Part,
    TaskResult,
    TaskStatus,
)

console = Console()


class A2AClient:
    """HTTP client that speaks the A2A protocol."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._http.aclose()

    async def fetch_agent_card(self, agent_url: str) -> AgentCard | None:
        """Fetch an agent's AgentCard from /.well-known/agent.json."""
        try:
            resp = await self._http.get(f"{agent_url}/.well-known/agent.json")
            resp.raise_for_status()
            return AgentCard(**resp.json())
        except Exception as e:
            console.print(f"[yellow]Failed to fetch AgentCard from {agent_url}: {e}[/yellow]")
            return None

    async def send_task(
        self,
        agent_url: str,
        skill_id: str,
        text: str,
        data: dict | None = None,
    ) -> TaskResult | None:
        """Send a task to an agent via JSON-RPC 2.0."""
        task_id = f"task-{uuid4().hex[:8]}"
        req_id = f"req-{uuid4().hex[:8]}"

        parts = [Part(type="text", text=text)]
        if data:
            parts.append(Part(type="data", data=data))

        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": req_id,
            "params": {
                "id": task_id,
                "skill_id": skill_id,
                "message": {
                    "role": "user",
                    "parts": [p.model_dump() for p in parts],
                },
            },
        }

        try:
            resp = await self._http.post(f"{agent_url}/a2a", json=payload)
            resp.raise_for_status()
            body = resp.json()

            if "error" in body and body["error"]:
                console.print(f"[red]A2A error from {agent_url}: {body['error']}[/red]")
                return None

            result_data = body.get("result", {})
            return TaskResult(
                id=result_data.get("id", task_id),
                status=TaskStatus(state=result_data.get("status", {}).get("state", "failed")),
                artifacts=[
                    Artifact(parts=[Part(**p) for p in art.get("parts", [])])
                    for art in result_data.get("artifacts", [])
                ],
            )
        except Exception as e:
            console.print(f"[red]A2A call failed to {agent_url}: {e}[/red]")
            return None

    def extract_text(self, result: TaskResult) -> str:
        """Extract text from a task result's artifacts."""
        texts = []
        for art in result.artifacts:
            for p in art.parts:
                if p.type == "text" and p.text:
                    texts.append(p.text)
        return " ".join(texts)

    def extract_data(self, result: TaskResult) -> dict:
        """Extract first data part from a task result."""
        for art in result.artifacts:
            for p in art.parts:
                if p.type == "data" and p.data:
                    return p.data
        return {}
