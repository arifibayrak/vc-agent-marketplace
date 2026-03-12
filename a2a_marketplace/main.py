"""
A2A VC Agent Marketplace - Demo Launcher

Starts the orchestrator and all 6 agents as independent HTTP servers,
then runs the deal flow via A2A protocol (JSON-RPC 2.0 over HTTP).

    python main.py
"""

import asyncio
import json
import os
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from a2a_marketplace.agents.llm_client import init_llm
from a2a_marketplace.agents.startup_a2a_agent import StartupA2AAgent
from a2a_marketplace.agents.vc_a2a_agent import VCA2AAgent
from a2a_marketplace.orchestrator.deal_flow import DealFlowEngine
from a2a_marketplace.orchestrator.server import app, set_deal_flow_engine, get_agent_urls

load_dotenv(override=True)

console = Console()

PROFILES_DIR = Path(__file__).parent / "agents" / "profiles"

STARTUP_CONFIGS = [
    ("ai_ml_startup.json", 8001),
    ("fintech_startup.json", 8002),
    ("healthtech_startup.json", 8003),
    ("cleantech_startup.json", 8004),
]

VC_CONFIGS = [
    ("early_stage_vc.json", 8010),
    ("growth_stage_vc.json", 8011),
]


def load_profile(filename: str) -> dict:
    with open(PROFILES_DIR / filename) as f:
        return json.load(f)


async def run_orchestrator():
    """Run the orchestrator HTTP server."""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_agent(agent):
    """Run a single A2A agent server."""
    await agent.run()


async def register_agents_and_run_deals():
    """Wait for agents to boot, register them, then run deal flow."""
    # Wait for all agent servers to start
    await asyncio.sleep(3)

    console.print("\n[yellow]Registering agents with orchestrator...[/yellow]")

    # Register all agents with the orchestrator
    agent_urls = []
    async with httpx.AsyncClient() as client:
        for _, port in STARTUP_CONFIGS + VC_CONFIGS:
            url = f"http://localhost:{port}"
            try:
                resp = await client.post(
                    "http://localhost:8000/register-agent",
                    json={"url": url},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    agent_urls.append(url)
            except Exception as e:
                console.print(f"[red]Failed to register {url}: {e}[/red]")

    console.print(f"[green]Registered {len(agent_urls)} agents[/green]\n")

    # Wait a moment then run deal flow
    await asyncio.sleep(1)

    engine = DealFlowEngine()
    set_deal_flow_engine(engine)
    await engine.run(agent_urls)

    # Keep running so agents stay alive for dashboard inspection
    console.print("\n[yellow]Deal flow complete. Dashboard at http://localhost:8000/dashboard[/yellow]")
    console.print("[dim]Press Ctrl+C to shut down.[/dim]\n")

    # Keep alive
    while True:
        await asyncio.sleep(60)


async def main():
    console.print(Panel(
        "[bold yellow]VC Agent Marketplace — A2A Protocol[/bold yellow]\n"
        "Agent-to-Agent communication via JSON-RPC 2.0 over HTTP\n\n"
        "[dim]Orchestrator:[/dim]  http://localhost:8000\n"
        "[dim]Dashboard:[/dim]    http://localhost:8000/dashboard\n"
        "[dim]API:[/dim]          http://localhost:8000/api/agents\n\n"
        "[dim]Startup agents:[/dim] ports 8001-8004\n"
        "[dim]VC agents:[/dim]     ports 8010-8011\n\n"
        "[dim]Each agent serves its AgentCard at /.well-known/agent.json[/dim]\n"
        "[dim]Orchestrator discovers agents, matches them, and drives deals via A2A tasks[/dim]",
        title="A2A Demo Mode",
        border_style="yellow",
    ))

    init_llm()

    # Create all agents
    agents = []
    for filename, port in STARTUP_CONFIGS:
        profile = load_profile(filename)
        agents.append(StartupA2AAgent(profile, port))

    for filename, port in VC_CONFIGS:
        profile = load_profile(filename)
        agents.append(VCA2AAgent(profile, port))

    # Run everything concurrently
    tasks = [
        run_orchestrator(),
        *[run_agent(agent) for agent in agents],
        register_agents_and_run_deals(),
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
