"""Deal flow orchestration — drives the full VC↔Startup lifecycle via A2A tasks."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from rich.console import Console

from a2a_marketplace.models.types import AgentCard, Deal, DealStatus
from a2a_marketplace.orchestrator import event_bus
from a2a_marketplace.orchestrator.a2a_client import A2AClient
from a2a_marketplace.orchestrator.matcher import compute_match_score

console = Console()

# Valid deal status transitions
_VALID_TRANSITIONS: dict[DealStatus, set[DealStatus]] = {
    DealStatus.INITIATED: {DealStatus.PITCH_SENT},
    DealStatus.PITCH_SENT: {DealStatus.IN_DILIGENCE, DealStatus.INTEREST, DealStatus.PASSED},
    DealStatus.IN_DILIGENCE: {DealStatus.INTEREST, DealStatus.PASSED},
    DealStatus.INTEREST: {DealStatus.CLOSED},
    DealStatus.PASSED: {DealStatus.CLOSED},
    DealStatus.CLOSED: set(),
}


class DealFlowEngine:
    """Orchestrates the deal flow between startup and VC agents via A2A protocol."""

    def __init__(self):
        self.client = A2AClient()
        self.agent_cards: dict[str, AgentCard] = {}  # url -> AgentCard
        self.deals: list[Deal] = []
        self._startups: list[AgentCard] = []
        self._vcs: list[AgentCard] = []

    async def discover_agents(self, agent_urls: list[str]):
        """Fetch AgentCards from all registered agents and classify them."""
        await event_bus.emit_orchestrator_event(
            f"Discovering {len(agent_urls)} agents via AgentCards..."
        )

        for url in agent_urls:
            card = await self.client.fetch_agent_card(url)
            if card:
                self.agent_cards[url] = card
                agent_type = card.metadata.get("agent_type", "unknown")
                if agent_type == "startup":
                    self._startups.append(card)
                elif agent_type == "vc":
                    self._vcs.append(card)

                await event_bus.emit_agent_event(
                    agent_type.upper(),
                    f"Discovered {card.name} ({agent_type}) at {url}",
                )

        await event_bus.emit_orchestrator_event(
            f"Discovery complete: {len(self._startups)} startups, {len(self._vcs)} VCs"
        )

    async def run_matching(self, min_score: float = 0.7) -> list[dict]:
        """Run matching algorithm for all VC-startup pairs."""
        await event_bus.emit_orchestrator_event("Running matching algorithm...")

        matches = []
        for vc_card in self._vcs:
            vc_profile = vc_card.metadata.get("profile", {})
            for startup_card in self._startups:
                startup_profile = startup_card.metadata.get("profile", {})
                score = compute_match_score(vc_profile, startup_profile)

                if score >= min_score:
                    matches.append({
                        "vc_card": vc_card,
                        "startup_card": startup_card,
                        "score": score,
                    })
                    await event_bus.emit_orchestrator_event(
                        f"Match: {vc_card.name} <-> {startup_card.name} (score: {score})"
                    )

        matches.sort(key=lambda m: m["score"], reverse=True)
        await event_bus.emit_orchestrator_event(f"Found {len(matches)} matches above {min_score}")
        return matches

    async def execute_deal(self, vc_card: AgentCard, startup_card: AgentCard, score: float):
        """Run the full deal lifecycle for one VC-startup pair."""
        deal_id = f"deal-{uuid4().hex[:8]}"
        deal = Deal(
            deal_id=deal_id,
            vc_agent_url=vc_card.url,
            startup_agent_url=startup_card.url,
            vc_name=vc_card.name,
            startup_name=startup_card.name,
            match_score=score,
        )
        self.deals.append(deal)

        vc_profile = vc_card.metadata.get("profile", {})
        startup_profile = startup_card.metadata.get("profile", {})

        await event_bus.emit_deal_event(
            f"Deal {deal_id}: {vc_card.name} <-> {startup_card.name} (score: {score})",
            deal_id=deal_id,
        )

        # Step 1: Request pitch from startup
        await event_bus.emit_a2a_event(
            f"tasks/send pitch_request -> {startup_card.name}"
        )
        pitch_result = await self.client.send_task(
            startup_card.url,
            skill_id="pitch_request",
            text=f"Please pitch your startup to {vc_card.name}.",
            data={"deal_id": deal_id, "vc_profile": vc_profile},
        )
        if not pitch_result or pitch_result.status.state != "completed":
            await event_bus.emit_deal_event(f"Deal {deal_id}: pitch failed", deal_id=deal_id)
            deal.status = DealStatus.CLOSED
            deal.outcome = "pitch_failed"
            return

        deal.status = DealStatus.PITCH_SENT
        pitch_text = self.client.extract_text(pitch_result)
        pitch_data = self.client.extract_data(pitch_result)
        await event_bus.emit_deal_event(f"Deal {deal_id}: pitch received", deal_id=deal_id)

        # Step 2: VC evaluates pitch → generates questions
        await event_bus.emit_a2a_event(
            f"tasks/send evaluate_pitch -> {vc_card.name}"
        )
        eval_result = await self.client.send_task(
            vc_card.url,
            skill_id="evaluate_pitch",
            text=f"Evaluate this pitch from {startup_card.name}.",
            data={
                "deal_id": deal_id,
                "startup_name": startup_card.name,
                "pitch_text": pitch_text,
                "key_metrics": pitch_data.get("key_metrics", startup_profile.get("metrics", {})),
                "funding_ask": pitch_data.get("funding_ask", startup_profile.get("funding_ask", 0)),
                "sector": startup_profile.get("sector", ""),
                "stage": startup_profile.get("stage", ""),
            },
        )
        if not eval_result or eval_result.status.state != "completed":
            await event_bus.emit_deal_event(f"Deal {deal_id}: evaluation failed", deal_id=deal_id)
            deal.status = DealStatus.CLOSED
            deal.outcome = "evaluation_failed"
            return

        eval_data = self.client.extract_data(eval_result)
        questions = eval_data.get("questions", [])
        deal.status = DealStatus.IN_DILIGENCE
        await event_bus.emit_deal_event(
            f"Deal {deal_id}: VC asked {len(questions)} questions", deal_id=deal_id
        )

        # Step 3: Startup answers due diligence questions
        await event_bus.emit_a2a_event(
            f"tasks/send due_diligence -> {startup_card.name}"
        )
        dd_result = await self.client.send_task(
            startup_card.url,
            skill_id="due_diligence",
            text="Answer these due diligence questions.",
            data={"deal_id": deal_id, "questions": questions},
        )
        if not dd_result or dd_result.status.state != "completed":
            await event_bus.emit_deal_event(f"Deal {deal_id}: DD answers failed", deal_id=deal_id)
            deal.status = DealStatus.CLOSED
            deal.outcome = "dd_failed"
            return

        answers_text = self.client.extract_text(dd_result)
        await event_bus.emit_deal_event(
            f"Deal {deal_id}: startup answered questions", deal_id=deal_id
        )

        # Step 4: VC makes investment decision
        await event_bus.emit_a2a_event(
            f"tasks/send investment_decision -> {vc_card.name}"
        )
        decision_result = await self.client.send_task(
            vc_card.url,
            skill_id="investment_decision",
            text=f"Make an investment decision on {startup_card.name}.",
            data={
                "deal_id": deal_id,
                "startup_name": startup_card.name,
                "pitch_text": pitch_text,
                "answers_text": answers_text,
                "key_metrics": pitch_data.get("key_metrics", {}),
                "funding_ask": pitch_data.get("funding_ask", 0),
                "sector": startup_profile.get("sector", ""),
                "stage": startup_profile.get("stage", ""),
            },
        )
        if not decision_result or decision_result.status.state != "completed":
            await event_bus.emit_deal_event(f"Deal {deal_id}: decision failed", deal_id=deal_id)
            deal.status = DealStatus.CLOSED
            deal.outcome = "decision_failed"
            return

        decision_data = self.client.extract_data(decision_result)
        decision = decision_data.get("decision", "pass")
        reasoning = decision_data.get("reasoning", "")
        next_steps = decision_data.get("next_steps", "")

        if decision == "interest":
            deal.status = DealStatus.INTEREST
        else:
            deal.status = DealStatus.PASSED

        deal.outcome = decision
        await event_bus.emit_deal_event(
            f"Deal {deal_id}: {vc_card.name} → {decision.upper()} on {startup_card.name}",
            deal_id=deal_id,
        )

        # Step 5: Notify startup of decision
        await event_bus.emit_a2a_event(
            f"tasks/send decision_notification -> {startup_card.name}"
        )
        await self.client.send_task(
            startup_card.url,
            skill_id="decision_notification",
            text=f"Investment decision from {vc_card.name}: {decision}",
            data={
                "deal_id": deal_id,
                "decision": decision,
                "reasoning": reasoning,
                "next_steps": next_steps,
                "vc_name": vc_card.name,
            },
        )

        # Close the deal
        deal.status = DealStatus.CLOSED
        await event_bus.emit_deal_event(
            f"Deal {deal_id}: CLOSED ({decision})", deal_id=deal_id
        )

    async def run(self, agent_urls: list[str]):
        """Full orchestration: discover → match → execute all deals."""
        await self.discover_agents(agent_urls)
        matches = await self.run_matching()

        if not matches:
            await event_bus.emit_orchestrator_event("No matches found. Deal flow complete.")
            return

        await event_bus.emit_orchestrator_event(
            f"Executing {len(matches)} deals via A2A protocol..."
        )

        for match in matches:
            await self.execute_deal(
                match["vc_card"],
                match["startup_card"],
                match["score"],
            )
            # Small delay between deals for readability
            await asyncio.sleep(0.5)

        await event_bus.emit_orchestrator_event(
            f"All {len(matches)} deals complete. "
            f"Interest: {sum(1 for d in self.deals if d.outcome == 'interest')}, "
            f"Pass: {sum(1 for d in self.deals if d.outcome == 'pass')}"
        )

        await self.client.close()
