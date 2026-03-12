"""A2A Startup Agent — handles pitch_request, due_diligence, and decision_notification tasks."""

from __future__ import annotations

import json

from rich.console import Console

from a2a_marketplace.agents.base_a2a_agent import BaseA2AAgent
from a2a_marketplace.agents.llm_client import think
from a2a_marketplace.models.types import Message, TaskResult

console = Console()

STARTUP_SKILLS = [
    {"id": "pitch_request", "name": "Pitch", "description": "Generate a tailored investor pitch"},
    {"id": "due_diligence", "name": "Due Diligence", "description": "Answer investor questions"},
    {"id": "decision_notification", "name": "Decision", "description": "Receive investment decision"},
]


class StartupA2AAgent(BaseA2AAgent):
    def __init__(self, profile: dict, port: int):
        super().__init__(profile, agent_type="startup", port=port, skills=STARTUP_SKILLS)
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        p = self.profile
        metrics = p.get("metrics", {})
        return (
            f"You are the AI agent representing {p['name']}, a {p.get('sector', '')} startup.\n"
            f"Stage: {p.get('stage', '')}\n"
            f"Funding ask: ${p.get('funding_ask', 0):,}\n"
            f"Elevator pitch: {p.get('elevator_pitch', '')}\n"
            f"MRR: ${metrics.get('mrr', 0):,}, Growth: {metrics.get('growth_rate', 0):.0%}, "
            f"Customers: {metrics.get('customers', 0)}\n"
            f"Team: {p.get('team_size', 0)} people, Founded: {p.get('founded_year', '')}, "
            f"Location: {p.get('location', '')}\n\n"
            "Respond professionally and persuasively. Highlight strengths, be honest about metrics."
        )

    async def handle_task(self, task_id: str, skill_id: str, message: Message) -> TaskResult:
        text = self.extract_text(message)
        data = self.extract_data(message)

        if skill_id == "pitch_request":
            return await self._handle_pitch(task_id, text, data)
        elif skill_id == "due_diligence":
            return await self._handle_due_diligence(task_id, text, data)
        elif skill_id == "decision_notification":
            return self._handle_decision(task_id, text, data)
        else:
            return self.make_response(task_id, f"Unknown skill: {skill_id}")

    async def _handle_pitch(self, task_id: str, text: str, data: dict) -> TaskResult:
        vc_profile = data.get("vc_profile", {})
        vc_name = vc_profile.get("name", "the investor")
        firm = vc_profile.get("firm_name", "")

        console.print(f"[green]{self.name}[/green] generating pitch for {vc_name} ({firm})")

        prompt = (
            f"Generate a compelling pitch for {vc_name} at {firm}.\n"
            f"They focus on: {', '.join(vc_profile.get('target_sectors', []))}\n"
            f"Stages: {', '.join(vc_profile.get('target_stages', []))}\n"
            f"Check size: ${vc_profile.get('check_size_min', 0):,} - ${vc_profile.get('check_size_max', 0):,}\n\n"
            "Include: elevator pitch, key metrics, funding ask, use of funds, competitive advantage."
        )

        response = await think(self.system_prompt, prompt)

        p = self.profile
        return self.make_response(task_id, response, {
            "key_metrics": p.get("metrics", {}),
            "funding_ask": p.get("funding_ask", 0),
            "sector": p.get("sector", ""),
            "stage": p.get("stage", ""),
        })

    async def _handle_due_diligence(self, task_id: str, text: str, data: dict) -> TaskResult:
        questions = data.get("questions", [])
        console.print(f"[green]{self.name}[/green] answering {len(questions)} questions")

        prompt = (
            f"Answer these due diligence questions from the investor:\n\n"
            + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
            + "\n\nProvide detailed, data-driven answers."
        )

        response = await think(self.system_prompt, prompt)

        return self.make_response(task_id, response, {
            "questions_answered": len(questions),
        })

    def _handle_decision(self, task_id: str, text: str, data: dict) -> TaskResult:
        decision = data.get("decision", "unknown")
        reasoning = data.get("reasoning", "")
        next_steps = data.get("next_steps", "")

        emoji = "+" if decision == "interest" else "-"
        console.print(
            f"[green]{self.name}[/green] received decision: "
            f"[{'green' if decision == 'interest' else 'red'}]{decision}[/]"
        )

        return self.make_response(task_id, f"Acknowledged: {decision}", {
            "acknowledged": True,
            "decision": decision,
        })
