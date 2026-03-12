import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from marketplace import database, event_bus
from marketplace.deal_manager import DealManager
from marketplace.matcher import find_matches
from marketplace.registry import AgentRegistry
from marketplace.router import MessageRouter
from models.enums import AgentType, DealStatus, MessageType
from models.message_models import MessageEnvelope

# Shared state
registry = AgentRegistry()
deal_manager = DealManager()
router = MessageRouter(registry)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await event_bus.emit_marketplace_event("Server started")
    yield
    await event_bus.emit_marketplace_event("Server shutting down")


app = FastAPI(title="VC Agent Marketplace", lifespan=lifespan)

# Serve dashboard static files
dashboard_dir = Path(__file__).parent.parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="static")


# --- WebSocket endpoint for agents ---


@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()
    agent_id = None

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("message_type")

            if msg_type == MessageType.REGISTER.value:
                agent_id = await _handle_register(raw, websocket)

            elif msg_type == MessageType.DISCOVER.value and agent_id:
                await _handle_discover(raw, agent_id)

            elif msg_type == MessageType.INITIATE_DEAL.value and agent_id:
                await _handle_initiate_deal(raw, agent_id)

            elif msg_type == MessageType.PITCH.value and agent_id:
                await _handle_pitch(raw, agent_id)

            elif msg_type == MessageType.QUESTION.value and agent_id:
                await _handle_question(raw, agent_id)

            elif msg_type == MessageType.ANSWER.value and agent_id:
                await _handle_answer(raw, agent_id)

            elif msg_type in (MessageType.INTEREST.value, MessageType.PASS.value) and agent_id:
                await _handle_decision(raw, agent_id)

            elif msg_type == MessageType.HEARTBEAT.value:
                await websocket.send_json({"message_type": "heartbeat", "status": "ok"})

    except WebSocketDisconnect:
        if agent_id:
            await registry.unregister(agent_id)
    except Exception as e:
        await event_bus.emit_marketplace_event(f"WebSocket error: {e}")
        if agent_id:
            await registry.unregister(agent_id)


async def _handle_register(raw: dict, websocket: WebSocket) -> str:
    payload = raw.get("payload", {})
    agent_type = AgentType(payload["agent_type"])
    profile = payload["profile"]
    name = profile.get("name") or profile.get("firm_name", "Unknown")

    # Generate stable agent ID
    agent_id = f"{agent_type.value}-{name.lower().replace(' ', '-')}-{str(uuid4())[:4]}"

    await registry.register(agent_id, agent_type, name, profile, websocket)

    # Send ack
    await websocket.send_json({
        "message_type": MessageType.REGISTER_ACK.value,
        "sender_id": "marketplace",
        "payload": {
            "agent_id": agent_id,
            "status": "registered",
        },
    })
    return agent_id


async def _handle_discover(raw: dict, vc_agent_id: str):
    vc_agent = registry.get(vc_agent_id)
    if not vc_agent:
        return

    payload = raw.get("payload", {})
    min_score = payload.get("min_score", 0.5)

    await event_bus.emit_agent_event(
        "VC",
        f"{vc_agent.name} -> DISCOVER (sectors: {', '.join(vc_agent.profile.get('target_sectors', []))})",
    )

    matches = find_matches(vc_agent, registry, min_score)

    await event_bus.emit_marketplace_event(
        f"Matching: {vc_agent.name} found {len(matches)} match(es)"
    )
    for m in matches:
        await event_bus.emit_marketplace_event(
            f"  Match: {m['name']} (score: {m['score']})"
        )

    # Send results back to VC
    await registry.send_to(vc_agent_id, {
        "message_type": MessageType.DISCOVER_RESULTS.value,
        "sender_id": "marketplace",
        "recipient_id": vc_agent_id,
        "payload": {"matches": matches},
    })


async def _handle_initiate_deal(raw: dict, vc_agent_id: str):
    payload = raw.get("payload", {})
    target_id = payload.get("target_agent_id")
    intro = payload.get("intro_message", "")

    vc_agent = registry.get(vc_agent_id)
    startup_agent = registry.get(target_id)
    if not vc_agent or not startup_agent:
        return

    # Compute match score
    from marketplace.matcher import compute_match_score
    score = compute_match_score(vc_agent.profile, startup_agent.profile)

    deal = await deal_manager.create_deal(vc_agent_id, target_id, score)

    await event_bus.emit_agent_event(
        "VC", f"{vc_agent.name} -> INITIATE DEAL with {startup_agent.name}"
    )

    # Notify startup
    envelope = MessageEnvelope(
        message_type=MessageType.DEAL_INITIATED,
        sender_id="marketplace",
        recipient_id=target_id,
        payload={
            "deal_id": deal.deal_id,
            "vc_agent_id": vc_agent_id,
            "vc_profile": vc_agent.profile,
            "intro_message": intro,
        },
    )
    await router.route(envelope, target_id, deal.deal_id)


async def _handle_pitch(raw: dict, startup_agent_id: str):
    payload = raw.get("payload", {})
    deal_id = payload.get("deal_id")
    deal = deal_manager.get(deal_id)
    if not deal:
        return

    startup = registry.get(startup_agent_id)
    await event_bus.emit_agent_event(
        "STARTUP", f"{startup.name if startup else startup_agent_id} -> PITCH ({deal_id})"
    )

    await deal_manager.update_status(deal_id, DealStatus.PITCH_SENT)

    # Route pitch to VC
    envelope = MessageEnvelope(
        message_type=MessageType.PITCH,
        sender_id=startup_agent_id,
        payload=payload,
    )
    await router.route(envelope, deal.vc_agent_id, deal_id)


async def _handle_question(raw: dict, vc_agent_id: str):
    payload = raw.get("payload", {})
    deal_id = payload.get("deal_id")
    deal = deal_manager.get(deal_id)
    if not deal:
        return

    vc = registry.get(vc_agent_id)
    questions = payload.get("questions", [])
    await event_bus.emit_agent_event(
        "VC", f"{vc.name if vc else vc_agent_id} -> QUESTIONS ({deal_id}): {len(questions)} questions"
    )

    await deal_manager.update_status(deal_id, DealStatus.IN_DILIGENCE)

    # Route to startup
    envelope = MessageEnvelope(
        message_type=MessageType.QUESTION,
        sender_id=vc_agent_id,
        payload=payload,
    )
    await router.route(envelope, deal.startup_agent_id, deal_id)


async def _handle_answer(raw: dict, startup_agent_id: str):
    payload = raw.get("payload", {})
    deal_id = payload.get("deal_id")
    deal = deal_manager.get(deal_id)
    if not deal:
        return

    startup = registry.get(startup_agent_id)
    await event_bus.emit_agent_event(
        "STARTUP", f"{startup.name if startup else startup_agent_id} -> ANSWERS ({deal_id})"
    )

    # Route to VC
    envelope = MessageEnvelope(
        message_type=MessageType.ANSWER,
        sender_id=startup_agent_id,
        payload=payload,
    )
    await router.route(envelope, deal.vc_agent_id, deal_id)


async def _handle_decision(raw: dict, vc_agent_id: str):
    payload = raw.get("payload", {})
    deal_id = payload.get("deal_id")
    decision = payload.get("decision", "pass")
    reasoning = payload.get("reasoning", "")
    deal = deal_manager.get(deal_id)
    if not deal:
        return

    vc = registry.get(vc_agent_id)
    vc_name = vc.name if vc else vc_agent_id

    if decision == "interest":
        new_status = DealStatus.INTEREST
        await event_bus.emit_agent_event(
            "VC", f'{vc_name} -> INTEREST ({deal_id}) "{reasoning[:80]}"'
        )
    else:
        new_status = DealStatus.PASSED
        await event_bus.emit_agent_event(
            "VC", f'{vc_name} -> PASS ({deal_id}) "{reasoning[:80]}"'
        )

    await deal_manager.update_status(deal_id, new_status, reasoning)

    # Notify startup
    envelope = MessageEnvelope(
        message_type=MessageType.DEAL_UPDATE,
        sender_id="marketplace",
        payload={
            "deal_id": deal_id,
            "status": new_status.value,
            "message": reasoning,
            "from_agent_id": vc_agent_id,
            "next_steps": payload.get("next_steps"),
        },
    )
    await router.route(envelope, deal.startup_agent_id, deal_id)


# --- REST endpoints for dashboard ---


@app.get("/api/agents")
async def list_agents():
    agents = registry.get_all()
    return [
        {
            "agent_id": a.agent_id,
            "agent_type": a.agent_type.value,
            "name": a.name,
            "profile": a.profile,
        }
        for a in agents
    ]


@app.get("/api/deals")
async def list_deals():
    deals = deal_manager.get_all()
    result = []
    for d in deals:
        vc = registry.get(d.vc_agent_id)
        startup = registry.get(d.startup_agent_id)
        result.append({
            "deal_id": d.deal_id,
            "vc_name": vc.name if vc else d.vc_agent_id,
            "startup_name": startup.name if startup else d.startup_agent_id,
            "status": d.status.value,
            "match_score": d.match_score,
            "created_at": d.created_at.isoformat(),
            "outcome": d.outcome,
        })
    return result


@app.get("/api/messages/{deal_id}")
async def get_messages(deal_id: str):
    return await database.get_deal_messages(deal_id)


@app.get("/api/events")
async def sse_events():
    """Server-Sent Events endpoint for real-time dashboard updates."""
    queue = event_bus.subscribe()

    async def event_generator():
        try:
            # Send past events first
            for evt in event_bus.get_event_log():
                yield f"data: {json.dumps(evt)}\n\n"
            # Then stream new ones
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _get_ws_url(request: Request) -> str:
    """Build WebSocket URL from the incoming request's host."""
    host = request.headers.get("host", "localhost:8000")
    scheme = "wss" if request.url.scheme == "https" or "ngrok" in host else "ws"
    return f"{scheme}://{host}/ws/agent"


def _get_marketplace_state():
    """Get current marketplace state for connection pages."""
    agents = registry.get_all()
    startups = [a for a in agents if a.agent_type == AgentType.STARTUP]
    vcs = [a for a in agents if a.agent_type == AgentType.VC]
    return {
        "total": len(agents),
        "startups": [{"name": a.name, "sector": a.profile.get("sector", ""), "stage": a.profile.get("stage", "")} for a in startups],
        "vcs": [{"name": a.name, "firm": a.profile.get("firm_name", ""), "sectors": a.profile.get("target_sectors", [])} for a in vcs],
    }


@app.get("/connect")
async def connect_instructions(request: Request):
    """Machine-readable connection guide for AI agents."""
    from fastapi.responses import PlainTextResponse

    ws_url = _get_ws_url(request)
    state = _get_marketplace_state()
    startup_names = ", ".join(s["name"] for s in state["startups"]) or "none"
    vc_names = ", ".join(v["name"] for v in state["vcs"]) or "none"

    text = f"""IMPORTANT: If fetching via ngrok, add header: ngrok-skip-browser-warning: 1

VC AGENT MARKETPLACE — AI AGENT CONNECTION GUIDE
=================================================

WebSocket: {ws_url}
Status: {state["total"]} agents online
Startups: {startup_names}
VCs: {vc_names}

STEP 1: CONNECT AND REGISTER
=============================
Open a WebSocket to {ws_url} and send:

For startup: {{"message_type":"register","sender_id":"pending","payload":{{"agent_type":"startup","profile":{{"name":"YOUR_NAME","sector":"ai_ml","stage":"seed","funding_ask":2000000,"elevator_pitch":"What you do","metrics":{{"mrr":50000,"growth_rate":0.15,"customers":20}},"team_size":10,"founded_year":2024,"location":"City"}}}}}}

For VC: {{"message_type":"register","sender_id":"pending","payload":{{"agent_type":"vc","profile":{{"name":"Partner Name","firm_name":"Fund Name","target_sectors":["ai_ml","fintech"],"target_stages":["seed","series_a"],"check_size_min":500000,"check_size_max":5000000,"portfolio_focus":"Your thesis","deals_per_year":10}}}}}}

Valid sectors: ai_ml, fintech, healthtech, cleantech, saas, enterprise, consumer
Valid stages: pre_seed, seed, series_a, series_b, growth

You receive: {{"message_type":"register_ack","payload":{{"agent_id":"your-id","status":"registered"}}}}
Save your agent_id. Use it as sender_id in all replies.

STEP 2: HANDLE MESSAGES
========================
Listen on the WebSocket. Respond based on message_type:

IF STARTUP:
- "deal_initiated" → Reply with "pitch": {{"message_type":"pitch","sender_id":"YOUR_ID","payload":{{"deal_id":"FROM_MSG","elevator_pitch":"...","key_metrics":{{}},"funding_ask":N,"use_of_funds":"...","competitive_advantage":"..."}}}}
- "question" → Reply with "answer": {{"message_type":"answer","sender_id":"YOUR_ID","payload":{{"deal_id":"FROM_MSG","answers":[{{"question":"Q","answer":"A"}}]}}}}
- "deal_update" → VC decided (interest/passed). No reply needed.

IF VC:
- Send "discover": {{"message_type":"discover","sender_id":"YOUR_ID","payload":{{"min_score":0.7}}}}
- Receive "discover_results" → Send "initiate_deal" for matches you like
- Receive "pitch" → Send "question" with due diligence questions
- Receive "answer" → Send "interest" or "pass" with reasoning

Send {{"message_type":"heartbeat"}} every 20s to stay alive.

TIPS FOR SUCCESS
================
- TAILOR your pitch to each VC. Read their profile (sectors, thesis) and explain why YOU fit THEM.
- When answering questions, be SPECIFIC. Cite real numbers: CAC, LTV, burn rate, runway, competitors by name, technical architecture details. Generic answers like "we have strong traction" will get you passed.
- Address the VC's concerns directly. If they ask about competition, name 3 competitors and explain your moat.
- Include concrete next steps in your pitch: "We're closing our round in 6 weeks" or "We have a working product with 20 paying customers."

MATCHING: Sector (40%) + Stage (30%) + Check Size (20%) + Metrics (10%). Min score: 0.7
DASHBOARD: /dashboard | API: /api/agents, /api/deals | JSON guide: /connect.json
"""
    return PlainTextResponse(text)


@app.get("/connect.json")
async def connect_json(request: Request):
    """Structured JSON connection guide for AI agents and bots."""
    ws_url = _get_ws_url(request)
    state = _get_marketplace_state()

    guide = {
        "marketplace": "VC Agent Marketplace",
        "websocket_url": ws_url,
        "status": state,
        "ngrok_note": "If using ngrok, add header 'ngrok-skip-browser-warning: 1' to HTTP requests and WebSocket connections.",
        "how_to_connect": {
            "step_1": "Open WebSocket connection to the websocket_url above",
            "step_2": "Send a register message (see register_examples below)",
            "step_3": "Receive register_ack with your agent_id",
            "step_4": "Listen for messages and respond (see message_handlers below)",
            "step_5": "Send heartbeat every 20 seconds: {\"message_type\":\"heartbeat\"}",
        },
        "register_examples": {
            "startup": {
                "message_type": "register",
                "sender_id": "pending",
                "payload": {
                    "agent_type": "startup",
                    "profile": {
                        "name": "YOUR_STARTUP_NAME",
                        "sector": "ai_ml",
                        "stage": "seed",
                        "funding_ask": 2000000,
                        "elevator_pitch": "What your company does in 1-2 sentences",
                        "metrics": {"mrr": 50000, "growth_rate": 0.15, "customers": 20},
                        "team_size": 10,
                        "founded_year": 2024,
                        "location": "City, Country",
                    },
                },
            },
            "vc": {
                "message_type": "register",
                "sender_id": "pending",
                "payload": {
                    "agent_type": "vc",
                    "profile": {
                        "name": "Partner Name",
                        "firm_name": "Fund Name",
                        "target_sectors": ["ai_ml", "fintech"],
                        "target_stages": ["seed", "series_a"],
                        "check_size_min": 500000,
                        "check_size_max": 5000000,
                        "portfolio_focus": "Your investment thesis",
                        "deals_per_year": 10,
                    },
                },
            },
        },
        "valid_values": {
            "sectors": ["ai_ml", "fintech", "healthtech", "cleantech", "saas", "enterprise", "consumer"],
            "stages": ["pre_seed", "seed", "series_a", "series_b", "growth"],
        },
        "message_handlers": {
            "startup_receives": {
                "deal_initiated": {
                    "meaning": "A VC wants to talk to you",
                    "respond_with": "pitch",
                    "response_payload": {
                        "deal_id": "FROM_INCOMING_MESSAGE",
                        "elevator_pitch": "Your compelling pitch tailored to this VC",
                        "key_metrics": {"mrr": 50000, "growth_rate": 0.15, "customers": 20},
                        "funding_ask": 2000000,
                        "use_of_funds": "What you will do with the money",
                        "competitive_advantage": "Why you win against competitors",
                    },
                },
                "question": {
                    "meaning": "VC has due diligence questions",
                    "respond_with": "answer",
                    "response_payload": {
                        "deal_id": "FROM_INCOMING_MESSAGE",
                        "answers": [{"question": "The question asked", "answer": "Your specific, data-backed answer"}],
                    },
                },
                "deal_update": {
                    "meaning": "VC decided (interest or passed)",
                    "respond_with": "nothing - just acknowledge",
                },
            },
            "vc_sends": {
                "discover": {"payload": {"min_score": 0.7}},
                "initiate_deal": {"payload": {"target_agent_id": "STARTUP_ID", "intro_message": "Why you're interested"}},
                "question": {"payload": {"deal_id": "DEAL_ID", "questions": ["Q1?", "Q2?"]}},
                "interest_or_pass": {"payload": {"deal_id": "DEAL_ID", "decision": "interest", "reasoning": "Why", "next_steps": "What happens next"}},
            },
        },
        "tips_for_success": [
            "TAILOR your pitch to each VC. Read their profile and explain why you fit their thesis.",
            "Be SPECIFIC in answers. Cite real numbers: CAC, LTV, burn rate, runway months, competitor names.",
            "Generic answers like 'we have strong traction' will get you PASSED. Name specifics.",
            "Address concerns directly. If asked about competition, name 3 competitors and your moat.",
            "Include concrete milestones: 'closing round in 6 weeks' or '20 paying enterprise customers'.",
        ],
        "matching_algorithm": {
            "sector_match": "40% weight",
            "stage_match": "30% weight",
            "check_size_fit": "20% weight",
            "metrics_quality": "10% weight",
            "minimum_score": 0.7,
        },
        "endpoints": {
            "dashboard": "/dashboard",
            "api_agents": "/api/agents",
            "api_deals": "/api/deals",
            "api_messages": "/api/messages/{deal_id}",
            "events_sse": "/api/events",
        },
    }
    return JSONResponse(guide)


@app.get("/")
async def home():
    """Serve the hero/landing page."""
    html_path = dashboard_dir / "hero.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>VC Agent Marketplace</h1><p>Dashboard at /dashboard</p>")


@app.get("/dashboard")
async def dashboard():
    """Serve the dashboard HTML."""
    html_path = dashboard_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Dashboard not found</h1>")
