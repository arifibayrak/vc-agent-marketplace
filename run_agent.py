"""
VC Agent Marketplace - Autonomous Agent Launcher

Launch a single agent that connects to the marketplace independently.

Usage:
    # Launch from a profile file
    python run_agent.py --profile agents/profiles/ai_ml_startup.json

    # Launch with inline config
    python run_agent.py --type startup --name "MyStartup" --sector ai_ml --stage seed --ask 2000000

    # Launch a VC agent
    python run_agent.py --profile agents/profiles/early_stage_vc.json

    # Connect to a remote marketplace
    python run_agent.py --profile agents/profiles/ai_ml_startup.json --url ws://marketplace.example.com/ws/agent
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv(override=True)

from agents.llm_client import init_llm
from agents.startup_agent import StartupAgent
from agents.vc_agent import VCAgent

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="Launch an autonomous agent")
    parser.add_argument("--profile", type=str, help="Path to agent profile JSON file")
    parser.add_argument("--type", choices=["startup", "vc"], help="Agent type (if not using --profile)")
    parser.add_argument("--name", type=str, help="Agent/company name")
    parser.add_argument("--sector", type=str, help="Sector (ai_ml, fintech, healthtech, cleantech, saas, enterprise)")
    parser.add_argument("--stage", type=str, help="Stage (pre_seed, seed, series_a, series_b, growth)")
    parser.add_argument("--ask", type=int, help="Funding ask in USD (startup only)")
    parser.add_argument("--pitch", type=str, help="Elevator pitch (startup only)")
    parser.add_argument("--url", type=str, default="ws://localhost:8000/ws/agent",
                        help="Marketplace WebSocket URL (default: ws://localhost:8000/ws/agent)")
    return parser.parse_args()


def build_startup_profile(args) -> dict:
    return {
        "name": args.name or "My Startup",
        "sector": args.sector or "ai_ml",
        "stage": args.stage or "seed",
        "funding_ask": args.ask or 2000000,
        "elevator_pitch": args.pitch or f"{args.name or 'Our startup'} is building innovative solutions in {args.sector or 'technology'}.",
        "metrics": {"mrr": 0, "growth_rate": 0, "customers": 0},
        "team_size": 5,
        "founded_year": 2024,
        "location": "Remote",
    }


def build_vc_profile(args) -> dict:
    sectors = [args.sector] if args.sector else ["ai_ml", "fintech", "saas"]
    stages = [args.stage] if args.stage else ["seed", "series_a"]
    return {
        "name": args.name or "VC Partner",
        "firm_name": args.name or "VC Fund",
        "target_sectors": sectors,
        "target_stages": stages,
        "check_size_min": 500000,
        "check_size_max": 10000000,
        "portfolio_focus": "Technology investments with strong founding teams.",
        "deals_per_year": 10,
    }


async def main():
    args = parse_args()

    # Load or build profile
    if args.profile:
        profile_path = Path(args.profile)
        if not profile_path.exists():
            console.print(f"[red]Profile not found: {args.profile}[/red]")
            sys.exit(1)
        with open(profile_path) as f:
            profile = json.load(f)
        # Detect type from profile
        agent_type = args.type or ("vc" if "firm_name" in profile else "startup")
    elif args.type:
        if args.type == "startup":
            profile = build_startup_profile(args)
        else:
            profile = build_vc_profile(args)
        agent_type = args.type
    else:
        console.print("[red]Provide --profile or --type. Run with --help for usage.[/red]")
        sys.exit(1)

    name = profile.get("name") or profile.get("firm_name", "Unknown")

    console.print(Panel(
        f"[bold {'green' if agent_type == 'startup' else 'cyan'}]{name}[/bold {'green' if agent_type == 'startup' else 'cyan'}]\n"
        f"Type: {agent_type.upper()}\n"
        f"Connecting to: {args.url}\n\n"
        "[dim]This agent runs autonomously. It will:[/dim]\n"
        + ("[dim]  - Register with the marketplace[/dim]\n"
           "[dim]  - Wait for VC outreach[/dim]\n"
           "[dim]  - Auto-pitch when contacted[/dim]\n"
           "[dim]  - Answer due diligence questions[/dim]\n"
           if agent_type == "startup" else
           "[dim]  - Register with the marketplace[/dim]\n"
           "[dim]  - Periodically discover startups[/dim]\n"
           "[dim]  - Initiate deals with matches[/dim]\n"
           "[dim]  - Evaluate pitches and decide[/dim]\n"
          ) +
        "[dim]  - Reconnect if disconnected[/dim]",
        title=f"Autonomous {agent_type.upper()} Agent",
        border_style="green" if agent_type == "startup" else "cyan",
    ))

    init_llm()

    if agent_type == "startup":
        agent = StartupAgent(profile)
    else:
        agent = VCAgent(profile)

    # Run with auto-reconnect
    while True:
        try:
            await agent.connect_and_run(marketplace_url=args.url)
        except KeyboardInterrupt:
            break
        console.print(f"[yellow]Reconnecting in 5 seconds...[/yellow]")
        await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped.[/yellow]")
