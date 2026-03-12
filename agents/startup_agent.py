import asyncio
import json

from agents.base import BaseAgent
from models.enums import AgentType, MessageType


class StartupAgent(BaseAgent):
    """Autonomous startup agent seeking funding.

    Behavior:
    - Registers with the marketplace on its own
    - Waits for VC outreach (marketplace routes deal initiations)
    - Autonomously generates tailored pitches using LLM
    - Answers due diligence questions using its profile data
    - Responds to investment decisions
    """

    def __init__(self, profile: dict):
        super().__init__(AgentType.STARTUP, profile)
        self._system_prompt = (
            f"You are {self.name}, a startup founder. "
            f"Your company: {profile.get('elevator_pitch', '')}. "
            f"Sector: {profile.get('sector', '')}. Stage: {profile.get('stage', '')}. "
            f"Funding ask: ${profile.get('funding_ask', 0):,}. "
            f"Metrics: {json.dumps(profile.get('metrics', {}))}. "
            f"Team size: {profile.get('team_size', 0)}. Location: {profile.get('location', '')}. "
            "You are passionate about your company and want to secure funding. "
            "Be professional, data-driven, and compelling. Keep responses concise."
        )

    async def handle_message(self, data: dict):
        msg_type = data.get("message_type")

        if msg_type == MessageType.DEAL_INITIATED.value:
            await self._handle_deal_initiated(data)
        elif msg_type == MessageType.QUESTION.value:
            await self._handle_questions(data)
        elif msg_type == MessageType.DEAL_UPDATE.value:
            await self._handle_deal_update(data)

    async def _handle_deal_initiated(self, data: dict):
        """A VC reached out. Autonomously generate and send a tailored pitch."""
        payload = data.get("payload", {})
        deal_id = payload.get("deal_id")
        vc_profile = payload.get("vc_profile", {})
        intro = payload.get("intro_message", "")
        vc_name = vc_profile.get("name") or vc_profile.get("firm_name", "A VC")

        self._log(f"Received deal initiation from {vc_name}")
        await asyncio.sleep(1)

        pitch_text = await self.llm_think(
            self._system_prompt,
            f"A VC ({vc_name}) from {vc_profile.get('firm_name', 'a fund')} has reached out: \"{intro}\". "
            f"Their focus: {vc_profile.get('portfolio_focus', 'technology investments')}. "
            "Generate a compelling 3-4 sentence pitch tailored to this VC's interests. "
            "Highlight why your startup is a good fit for their portfolio."
        )

        await self.send_message(MessageType.PITCH, {
            "deal_id": deal_id,
            "elevator_pitch": pitch_text,
            "key_metrics": self.profile.get("metrics", {}),
            "funding_ask": self.profile.get("funding_ask", 0),
            "use_of_funds": "Product development, team expansion, and market growth",
            "competitive_advantage": f"Proprietary technology in {self.profile.get('sector', 'our space')} with strong early traction",
        })

    async def _handle_questions(self, data: dict):
        """Autonomously answer VC's due diligence questions using LLM."""
        payload = data.get("payload", {})
        deal_id = payload.get("deal_id")
        questions = payload.get("questions", [])

        self._log(f"Answering {len(questions)} questions...")

        answers = []
        for q in questions:
            answer_text = await self.llm_think(
                self._system_prompt,
                f"A VC investor asks: \"{q}\"\n"
                f"Answer this question based on your startup's profile and metrics. "
                "Be specific, data-driven, and honest. Keep it to 2-3 sentences."
            )
            answers.append({"question": q, "answer": answer_text})

        await self.send_message(MessageType.ANSWER, {
            "deal_id": deal_id,
            "answers": answers,
        })

    async def _handle_deal_update(self, data: dict):
        """React to VC's investment decision."""
        payload = data.get("payload", {})
        status = payload.get("status", "")
        message = payload.get("message", "")
        next_steps = payload.get("next_steps")

        if status == "interest":
            self._log(f"VC is interested: {message[:100]}")
            if next_steps:
                self._log(f"Next steps: {next_steps}")
        elif status == "passed":
            self._log(f"VC passed: {message[:100]}")
        else:
            self._log(f"Deal update: {status} - {message[:80]}")
