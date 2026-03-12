"""Event bus for SSE broadcasting and Rich terminal logging."""

import asyncio
import json
from datetime import datetime, timezone

from rich.console import Console
from rich.text import Text

console = Console()

_subscribers: list[asyncio.Queue] = []
_event_log: list[dict] = []


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


async def publish_event(event_type: str, data: dict):
    event = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _event_log.append(event)

    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)

    _log_event(event_type, data)


def _log_event(event_type: str, data: dict):
    ts = _now()
    source = data.get("source", "SYSTEM")
    message = data.get("message", "")

    color_map = {
        "ORCHESTRATOR": "bold yellow",
        "STARTUP": "bold green",
        "VC": "bold cyan",
        "DEAL": "bold magenta",
        "A2A": "bold blue",
        "SYSTEM": "bold white",
    }
    style = color_map.get(source, "white")

    text = Text()
    text.append(f"[{ts}] ", style="dim")
    text.append(f"{source:<14}", style=style)
    text.append(f" {message}")
    console.print(text)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue):
    if q in _subscribers:
        _subscribers.remove(q)


def get_event_log() -> list[dict]:
    return list(_event_log)


async def emit_agent_event(source: str, message: str, **extra):
    await publish_event("agent", {"source": source, "message": message, **extra})


async def emit_deal_event(message: str, deal_id: str | None = None, **extra):
    await publish_event("deal", {"source": "DEAL", "message": message, "deal_id": deal_id, **extra})


async def emit_a2a_event(message: str, **extra):
    await publish_event("a2a", {"source": "A2A", "message": message, **extra})


async def emit_orchestrator_event(message: str, **extra):
    await publish_event("orchestrator", {"source": "ORCHESTRATOR", "message": message, **extra})
