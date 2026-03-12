"""
VC Agent Marketplace - Demo Launcher

Convenience script that starts the marketplace server AND launches
all 6 demo agents. For production, run them separately:

    Terminal 1:  python run_server.py
    Terminal 2:  python run_agent.py --profile agents/profiles/ai_ml_startup.json
    Terminal 3:  python run_agent.py --profile agents/profiles/early_stage_vc.json
    ...

Each agent is autonomous - it connects, registers, and acts independently.
"""

import asyncio
import json
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from agents.llm_client import init_llm
from agents.startup_agent import StartupAgent
from agents.vc_agent import VCAgent

load_dotenv(override=True)

console = Console()

PROFILES_DIR = Path(__file__).parent / "agents" / "profiles"


def load_profile(filename: str) -> dict:
    with open(PROFILES_DIR / filename) as f:
        return json.load(f)


async def run_server():
    """Run the FastAPI server."""
    config = uvicorn.Config(
        "marketplace.server:app",
        host=os.getenv("MARKETPLACE_HOST", "0.0.0.0"),
        port=int(os.getenv("MARKETPLACE_PORT", "8000")),
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_agents():
    """Launch all 6 agents autonomously with staggered delays."""
    await asyncio.sleep(1.5)

    startup_profiles = [
        ("ai_ml_startup.json", 0.5),
        ("fintech_startup.json", 1.0),
        ("healthtech_startup.json", 1.5),
        ("cleantech_startup.json", 2.0),
    ]
    vc_profiles = [
        ("early_stage_vc.json", 3.5),
        ("growth_stage_vc.json", 4.5),
    ]

    tasks = []

    for filename, delay in startup_profiles:
        profile = load_profile(filename)
        agent = StartupAgent(profile)
        tasks.append(agent.connect_and_run(startup_delay=delay))

    for filename, delay in vc_profiles:
        profile = load_profile(filename)
        agent = VCAgent(profile)
        tasks.append(agent.connect_and_run(startup_delay=delay))

    await asyncio.gather(*tasks)


async def main():
    """Run the marketplace server and all agents concurrently."""
    port = int(os.getenv("MARKETPLACE_PORT", "8000"))

    console.print(Panel(
        "[bold yellow]VC Agent Marketplace[/bold yellow]\n"
        "An intermediary connecting startup agents with VC agents\n\n"
        f"[dim]Home:[/dim]      http://localhost:{port}\n"
        f"[dim]Dashboard:[/dim] http://localhost:{port}/dashboard\n"
        f"[dim]API:[/dim]       http://localhost:{port}/api/agents\n\n"
        "[dim]Launching 4 startup agents + 2 VC agents autonomously...[/dim]\n"
        "[dim]Each agent connects, registers, and acts on its own.[/dim]\n\n"
        "[dim]To add more agents while running:[/dim]\n"
        "[dim]  python run_agent.py --profile your_profile.json[/dim]",
        title="Demo Mode",
        border_style="yellow",
    ))

    init_llm()

    await asyncio.gather(
        run_server(),
        run_agents(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
