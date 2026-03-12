from uuid import uuid4

from marketplace import database, event_bus
from models.deal_models import Deal
from models.enums import DealStatus

# Valid status transitions
_VALID_TRANSITIONS: dict[DealStatus, set[DealStatus]] = {
    DealStatus.INITIATED: {DealStatus.PITCH_SENT},
    DealStatus.PITCH_SENT: {DealStatus.IN_DILIGENCE, DealStatus.INTEREST, DealStatus.PASSED},
    DealStatus.IN_DILIGENCE: {DealStatus.INTEREST, DealStatus.PASSED},
    DealStatus.INTEREST: {DealStatus.CLOSED},
    DealStatus.PASSED: {DealStatus.CLOSED},
    DealStatus.CLOSED: set(),
}


class DealManager:
    """Manages deal lifecycle and state transitions."""

    def __init__(self):
        self._deals: dict[str, Deal] = {}

    async def create_deal(self, vc_agent_id: str, startup_agent_id: str,
                          match_score: float) -> Deal:
        deal_id = f"deal-{str(uuid4())[:8]}"
        deal = Deal(
            deal_id=deal_id,
            vc_agent_id=vc_agent_id,
            startup_agent_id=startup_agent_id,
            status=DealStatus.INITIATED,
            match_score=match_score,
        )
        self._deals[deal_id] = deal
        await database.save_deal(deal_id, vc_agent_id, startup_agent_id, DealStatus.INITIATED.value, match_score)
        await event_bus.emit_deal_event(
            f"Deal {deal_id} created: {vc_agent_id} <-> {startup_agent_id} (score: {match_score})",
            deal_id=deal_id,
        )
        return deal

    async def update_status(self, deal_id: str, new_status: DealStatus,
                            outcome: str | None = None) -> Deal | None:
        deal = self._deals.get(deal_id)
        if not deal:
            return None

        valid_next = _VALID_TRANSITIONS.get(deal.status, set())
        if new_status not in valid_next:
            await event_bus.emit_deal_event(
                f"Invalid transition: {deal.status.value} -> {new_status.value}",
                deal_id=deal_id,
            )
            return None

        deal.status = new_status
        if outcome:
            deal.outcome = outcome
        await database.update_deal_status(deal_id, new_status.value, outcome)
        await event_bus.emit_deal_event(
            f"Deal {deal_id} status: {new_status.value}" + (f" - {outcome}" if outcome else ""),
            deal_id=deal_id,
        )
        return deal

    def get(self, deal_id: str) -> Deal | None:
        return self._deals.get(deal_id)

    def get_all(self) -> list[Deal]:
        return list(self._deals.values())

    def get_by_agent(self, agent_id: str) -> list[Deal]:
        return [d for d in self._deals.values()
                if d.vc_agent_id == agent_id or d.startup_agent_id == agent_id]
