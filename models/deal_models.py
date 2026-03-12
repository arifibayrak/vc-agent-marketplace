from datetime import datetime, timezone

from pydantic import BaseModel, Field

from models.enums import DealStatus


class Deal(BaseModel):
    deal_id: str
    vc_agent_id: str
    startup_agent_id: str
    status: DealStatus = DealStatus.INITIATED
    match_score: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    outcome: str | None = None
