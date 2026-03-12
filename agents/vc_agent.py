import asyncio
import json

from agents.base import BaseAgent
from models.enums import AgentType, MessageType


class VCAgent(BaseAgent):
    """Autonomous VC agent that sources deals independently.

    Behavior:
    - Registers with the marketplace on its own
    - Periodically discovers new startups (every 30s)
    - Initiates deals with strong matches
    - Evaluates pitches using LLM
    - Asks due diligence questions
    - Makes investment decisions autonomously
    """

    def __init__(self, profile: dict):
        super().__init__(AgentType.VC, profile)
        self._system_prompt = (
            f"You are {self.name}, a partner at {profile.get('firm_name', 'a VC firm')}. "
            f"Investment thesis: {profile.get('portfolio_focus', '')}. "
            f"Target sectors: {', '.join(profile.get('target_sectors', []))}. "
            f"Target stages: {', '.join(profile.get('target_stages', []))}. "
            f"Check size: ${profile.get('check_size_min', 0):,} - ${profile.get('check_size_max', 0):,}. "
            "You are analytical, ask tough questions, and make data-driven investment decisions. "
            "Be professional and concise."
        )
        self._pending_deals: dict[str, dict] = {}
        self._seen_startups: set[str] = set()  # Track already-contacted startups
        self._discovery_task = None

    async def on_registered(self):
        """Start autonomous behavior after registration."""
        # Initial discovery
        await asyncio.sleep(1)
        await self._discover()
        # Start periodic discovery loop
        self._discovery_task = asyncio.create_task(self._periodic_discovery())

    async def _periodic_discovery(self):
        """Periodically scan for new startups. This runs autonomously."""
        while self._running:
            await asyncio.sleep(30)
            if self._ws:
                self._log("Scanning for new startups...")
                await self._discover()

    async def _discover(self):
        await self.send_message(MessageType.DISCOVER, {
            "sectors": self.profile.get("target_sectors", []),
            "stages": self.profile.get("target_stages", []),
            "min_score": 0.7,
        })

    async def handle_message(self, data: dict):
        msg_type = data.get("message_type")

        if msg_type == MessageType.DISCOVER_RESULTS.value:
            await self._handle_discover_results(data)
        elif msg_type == MessageType.PITCH.value:
            await self._handle_pitch(data)
        elif msg_type == MessageType.ANSWER.value:
            await self._handle_answers(data)

    async def _handle_discover_results(self, data: dict):
        """Process matching results and autonomously initiate deals with new matches."""
        payload = data.get("payload", {})
        matches = payload.get("matches", [])

        # Filter out already-contacted startups
        new_matches = [m for m in matches if m["agent_id"] not in self._seen_startups]

        if not new_matches:
            if not matches:
                self._log("No matching startups found.")
            return

        self._log(f"Found {len(new_matches)} new matching startup(s)")

        for i, match in enumerate(new_matches):
            self._seen_startups.add(match["agent_id"])
            await asyncio.sleep(2 + i * 3)

            intro = await self.llm_think(
                self._system_prompt,
                f"You found a matching startup: {match['name']} in {match['sector']} "
                f"(stage: {match['stage']}, match score: {match['score']}). "
                f"Their pitch: \"{match.get('elevator_pitch', 'N/A')}\". "
                "Write a 2-sentence introduction message expressing your interest and why you think "
                "this could be a good fit for your fund. Be specific about what excites you."
            )

            self._log(f"Initiating deal with {match['name']}...")
            await self.send_message(MessageType.INITIATE_DEAL, {
                "target_agent_id": match["agent_id"],
                "intro_message": intro,
            })

    async def _handle_pitch(self, data: dict):
        """Autonomously evaluate pitch and ask follow-up questions."""
        payload = data.get("payload", {})
        deal_id = payload.get("deal_id")
        pitch = payload.get("elevator_pitch", "")
        metrics = payload.get("key_metrics", {})
        funding_ask = payload.get("funding_ask", 0)

        self._log(f"Evaluating pitch for deal {deal_id}...")
        await asyncio.sleep(1)

        self._pending_deals[deal_id] = {
            "pitch": pitch,
            "metrics": metrics,
            "funding_ask": funding_ask,
        }

        questions_raw = await self.llm_think(
            self._system_prompt,
            f"A startup pitched you:\n\"{pitch}\"\n\n"
            f"Key metrics: {json.dumps(metrics)}\n"
            f"Funding ask: ${funding_ask:,}\n\n"
            "Generate exactly 3 critical due diligence questions. "
            "Focus on: unit economics, competitive moat, and growth trajectory. "
            'Return as a JSON array of strings, e.g. ["Q1?", "Q2?", "Q3?"]'
        )

        try:
            questions = json.loads(questions_raw)
            if not isinstance(questions, list):
                questions = [questions_raw]
        except json.JSONDecodeError:
            questions = [q.strip().strip('"').strip("- ") for q in questions_raw.split("\n") if q.strip()]
            if not questions:
                questions = ["What is your current burn rate and runway?",
                             "Who are your main competitors?",
                             "What is your customer acquisition cost?"]

        questions = questions[:3]

        self._log(f"Asking {len(questions)} questions for deal {deal_id}")
        await self.send_message(MessageType.QUESTION, {
            "deal_id": deal_id,
            "questions": questions,
        })

    async def _handle_answers(self, data: dict):
        """Autonomously evaluate answers and make investment decision."""
        payload = data.get("payload", {})
        deal_id = payload.get("deal_id")
        answers = payload.get("answers", [])

        self._log(f"Making decision on deal {deal_id}...")
        await asyncio.sleep(1)

        deal_info = self._pending_deals.get(deal_id, {})
        pitch = deal_info.get("pitch", "")
        metrics = deal_info.get("metrics", {})

        qa_text = "\n".join([
            f"Q: {a.get('question', 'N/A')}\nA: {a.get('answer', 'N/A')}"
            for a in answers
        ])

        decision_text = await self.llm_think(
            self._system_prompt,
            f"Based on the following, make an investment decision:\n\n"
            f"PITCH: {pitch}\n\n"
            f"METRICS: {json.dumps(metrics)}\n\n"
            f"DUE DILIGENCE Q&A:\n{qa_text}\n\n"
            "Decide: INTEREST or PASS.\n"
            'Respond in this exact JSON format: {{"decision": "interest" or "pass", "reasoning": "2-3 sentences", "next_steps": "if interested, what next"}}\n'
            "Be honest and analytical."
        )

        try:
            decision_data = json.loads(decision_text)
        except json.JSONDecodeError:
            if "interest" in decision_text.lower() and "pass" not in decision_text.lower()[:20]:
                decision_data = {
                    "decision": "interest",
                    "reasoning": decision_text[:200],
                    "next_steps": "Schedule a partner meeting",
                }
            else:
                decision_data = {
                    "decision": "pass",
                    "reasoning": decision_text[:200],
                }

        decision = decision_data.get("decision", "pass")
        reasoning = decision_data.get("reasoning", "No reasoning provided")
        next_steps = decision_data.get("next_steps")

        msg_type = MessageType.INTEREST if decision == "interest" else MessageType.PASS
        await self.send_message(msg_type, {
            "deal_id": deal_id,
            "decision": decision,
            "reasoning": reasoning,
            "next_steps": next_steps,
        })

        self._pending_deals.pop(deal_id, None)
