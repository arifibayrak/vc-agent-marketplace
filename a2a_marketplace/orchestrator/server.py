"""Orchestrator HTTP server — agent registration, dashboard, SSE, REST API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from a2a_marketplace.orchestrator import event_bus

app = FastAPI(title="VC Agent Marketplace — A2A Orchestrator")

# Registered agent URLs
_agent_urls: list[str] = []
_agent_cards: dict[str, dict] = {}  # url -> card data (populated after discovery)

# Deal data (populated by deal_flow engine via set_deal_flow_engine)
_deal_flow_engine = None

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


def set_deal_flow_engine(engine):
    global _deal_flow_engine
    _deal_flow_engine = engine


def get_agent_urls() -> list[str]:
    return list(_agent_urls)


# ── Agent Registration ────────────────────────────────────────────────

@app.post("/register-agent")
async def register_agent(request: Request):
    body = await request.json()
    url = body.get("url", "").rstrip("/")
    if not url:
        return JSONResponse({"error": "url required"}, status_code=400)

    if url not in _agent_urls:
        _agent_urls.append(url)
        await event_bus.emit_orchestrator_event(f"Agent registered: {url}")

    return {"status": "registered", "url": url}


# ── REST API ──────────────────────────────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    if _deal_flow_engine:
        agents = []
        for url, card in _deal_flow_engine.agent_cards.items():
            agents.append({
                "url": url,
                "name": card.name,
                "type": card.metadata.get("agent_type", "unknown"),
                "description": card.description,
                "skills": [s.model_dump() for s in card.skills],
            })
        return agents
    return [{"url": url} for url in _agent_urls]


@app.get("/api/deals")
async def list_deals():
    if _deal_flow_engine:
        return [d.model_dump() for d in _deal_flow_engine.deals]
    return []


@app.get("/api/events-log")
async def events_log():
    return event_bus.get_event_log()


# ── SSE ───────────────────────────────────────────────────────────────

@app.get("/api/events")
async def sse_events():
    queue = event_bus.subscribe()

    async def stream():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            event_bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Dashboard ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    html_file = DASHBOARD_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text())
    return HTMLResponse("<h1>A2A VC Agent Marketplace</h1><p><a href='/dashboard'>Dashboard</a></p>")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_file = DASHBOARD_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text())
    return HTMLResponse("<h1>Dashboard not found</h1>")


# Mount static files for CSS/JS
if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")
