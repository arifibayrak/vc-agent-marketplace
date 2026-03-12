import asyncio
import json
from datetime import datetime, timezone

from rich.console import Console
from rich.text import Text

console = Console()

# SSE subscribers
_subscribers: list[asyncio.Queue] = []

# Event log for dashboard initial load
_event_log: list[dict] = []


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


async def publish_event(event_type: str, data: dict):
    """Publish an event to all SSE subscribers and log it."""
    event = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _event_log.append(event)

    # Push to all SSE subscribers
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)

    # Rich terminal logging
    _log_event(event_type, data)


def _log_event(event_type: str, data: dict):
    """Pretty-print events to terminal using Rich."""
    ts = _now()
    source = data.get("source", "SYSTEM")
    message = data.get("message", "")

    color_map = {
        "MARKETPLACE": "bold yellow",
        "STARTUP": "bold green",
        "VC": "bold cyan",
        "DEAL": "bold magenta",
        "SYSTEM": "bold white",
    }
    style = color_map.get(source, "white")

    text = Text()
    text.append(f"[{ts}] ", style="dim")
    text.append(f"{source:<12}", style=style)
    text.append(f" {message}")
    console.print(text)


def subscribe() -> asyncio.Queue:
    """Create a new SSE subscriber queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue):
    """Remove an SSE subscriber."""
    if q in _subscribers:
        _subscribers.remove(q)


def get_event_log() -> list[dict]:
    """Get all past events (for dashboard initial load)."""
    return list(_event_log)


async def emit_agent_event(source: str, message: str, **extra):
    await publish_event("agent", {"source": source, "message": message, **extra})


async def emit_deal_event(message: str, deal_id: str | None = None, **extra):
    await publish_event("deal", {"source": "DEAL", "message": message, "deal_id": deal_id, **extra})


async def emit_marketplace_event(message: str, **extra):
    await publish_event("marketplace", {"source": "MARKETPLACE", "message": message, **extra})
