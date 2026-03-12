"""A2A VC Agent — handles evaluate_pitch and investment_decision tasks."""

from __future__ import annotations

import json

from rich.console import Console

from a2a_marketplace.agents.base_a2a_agent import BaseA2AAgent
from a2a_marketplace.agents.llm_client import think
from a2a_marketplace.models.types import Message, TaskResult

console = Console()

VC_SKILLS = [
    {"id": "evaluate_pitch", "name": "Evaluate Pitch", "description": "Review startup pitch and ask questions"},
    {"id": "investment_decision", "name": "Investment Decision", "description": "Make interest/pass decision"},
]


class VCA2AAgent(BaseA2AAgent):
    def __init__(self, profile: dict, port: int):
        super().__init__(profile, agent_type="vc", port=port, skills=VC_SKILLS)
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        p = self.profile
        return (
            f"You are the AI agent for {p['name']}, a partner at {p.get('firm_name', '')}.\n"
            f"Investment focus: {', '.join(p.get('target_sectors', []))}\n"
            f"Target stages: {', '.join(p.get('target_stages', []))}\n"
            f"Check size: ${p.get('check_size_min', 0):,} - ${p.get('check_size_max', 0):,}\n"
            f"Portfolio focus: {p.get('portfolio_focus', '')}\n"
            f"Deals per year: {p.get('deals_per_year', 0)}\n\n"
            "Evaluate startups rigorously. Ask sharp due diligence questions. "
            "Make data-driven investment decisions."
        )

    async def handle_task(self, task_id: str, skill_id: str, message: Message) -> TaskResult:
        text = self.extract_text(message)
        data = self.extract_data(message)

        if skill_id == "evaluate_pitch":
            return await self._handle_evaluate_pitch(task_id, text, data)
        elif skill_id == "investment_decision":
            return await self._handle_investment_decision(task_id, text, data)
        else:
            return self.make_response(task_id, f"Unknown skill: {skill_id}")

    async def _handle_evaluate_pitch(self, task_id: str, text: str, data: dict) -> TaskResult:
        startup_name = data.get("startup_name", "the startup")
        pitch_text = data.get("pitch_text", text)

        console.print(f"[cyan]{self.name}[/cyan] evaluating pitch from {startup_name}")

        prompt = (
            f"A startup called {startup_name} has pitched you.\n\n"
            f"PITCH:\n{pitch_text}\n\n"
            f"Metrics: {json.dumps(data.get('key_metrics', {}))}\n"
            f"Sector: {data.get('sector', 'unknown')}, Stage: {data.get('stage', 'unknown')}\n"
            f"Funding ask: ${data.get('funding_ask', 0):,}\n\n"
            "Generate 3 critical due diligence questions. "
            "Return ONLY a JSON array of 3 question strings."
        )

        response = await think(self.system_prompt, prompt)

        # Parse questions from response
        questions = self._parse_questions(response)

        return self.make_response(task_id, response, {
            "questions": questions,
            "startup_name": startup_name,
        })

    async def _handle_investment_decision(self, task_id: str, text: str, data: dict) -> TaskResult:
        startup_name = data.get("startup_name", "the startup")
        answers_text = data.get("answers_text", text)
        pitch_text = data.get("pitch_text", "")

        console.print(f"[cyan]{self.name}[/cyan] making decision on {startup_name}")

        prompt = (
            f"Make an investment decision on {startup_name}.\n\n"
            f"PITCH:\n{pitch_text}\n\n"
            f"DUE DILIGENCE ANSWERS:\n{answers_text}\n\n"
            f"Sector: {data.get('sector', 'unknown')}, Stage: {data.get('stage', 'unknown')}\n"
            f"Funding ask: ${data.get('funding_ask', 0):,}\n\n"
            "Decide: interest or pass.\n"
            'Return ONLY JSON: {"decision": "interest"|"pass", "reasoning": "...", "next_steps": "..."}'
        )

        response = await think(self.system_prompt, prompt)
        decision_data = self._parse_decision(response)

        decision = decision_data.get("decision", "pass")
        color = "green" if decision == "interest" else "red"
        console.print(
            f"[cyan]{self.name}[/cyan] decision on {startup_name}: [{color}]{decision}[/]"
        )

        return self.make_response(task_id, response, decision_data)

    def _parse_questions(self, response: str) -> list[str]:
        """Try to parse a JSON array of questions from LLM response."""
        try:
            # Try direct JSON parse
            parsed = json.loads(response.strip())
            if isinstance(parsed, list):
                return [str(q) for q in parsed[:3]]
        except json.JSONDecodeError:
            pass

        # Try to find JSON array in response
        import re
        match = re.search(r'\[.*?\]', response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return [str(q) for q in parsed[:3]]
            except json.JSONDecodeError:
                pass

        # Fallback: split by newlines
        lines = [l.strip().lstrip("0123456789.-) ") for l in response.strip().split("\n") if l.strip()]
        return lines[:3] if lines else [
            "What is your current burn rate?",
            "Who are your main competitors?",
            "What is your customer acquisition cost?",
        ]

    def _parse_decision(self, response: str) -> dict:
        """Try to parse decision JSON from LLM response."""
        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, dict) and "decision" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        import re
        match = re.search(r'\{.*?\}', response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, dict) and "decision" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # Fallback
        lower = response.lower()
        if "interest" in lower and "pass" not in lower:
            return {"decision": "interest", "reasoning": response, "next_steps": "Schedule follow-up"}
        return {"decision": "pass", "reasoning": response, "next_steps": None}
