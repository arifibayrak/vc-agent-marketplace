"""
VC Agent Marketplace - Standalone Server

Run the marketplace server independently. Agents connect autonomously.

Usage:
    python run_server.py
    python run_server.py --port 8000
"""

import asyncio
import os

import uvicorn
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv(override=True)

console = Console()


async def main():
    port = int(os.getenv("MARKETPLACE_PORT", "8000"))
    host = os.getenv("MARKETPLACE_HOST", "0.0.0.0")

    console.print(Panel(
        "[bold yellow]VC Agent Marketplace Server[/bold yellow]\n\n"
        f"[dim]Home:[/dim]      http://localhost:{port}\n"
        f"[dim]Dashboard:[/dim] http://localhost:{port}/dashboard\n"
        f"[dim]API:[/dim]       http://localhost:{port}/api/agents\n"
        f"[dim]WebSocket:[/dim] ws://localhost:{port}/ws/agent\n\n"
        "[dim]Agents can connect autonomously via WebSocket.[/dim]\n"
        "[dim]Run[/dim] python run_agent.py --help [dim]to launch an agent.[/dim]",
        title="Marketplace Server",
        border_style="yellow",
    ))

    config = uvicorn.Config(
        "marketplace.server:app",
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")
