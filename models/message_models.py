from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from models.enums import AgentType, FundingStage, MessageType, Sector


class MessageEnvelope(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    message_type: MessageType
    sender_id: str
    recipient_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None
    payload: dict = Field(default_factory=dict)


# --- Payload models for type-safe construction ---


class RegisterPayload(BaseModel):
    agent_type: AgentType
    profile: dict


class DiscoverPayload(BaseModel):
    sectors: list[Sector] | None = None
    stages: list[FundingStage] | None = None
    min_score: float = 0.5


class DiscoverResultItem(BaseModel):
    agent_id: str
    name: str
    sector: Sector
    stage: FundingStage
    score: float
    elevator_pitch: str


class DiscoverResultsPayload(BaseModel):
    matches: list[DiscoverResultItem]


class InitiateDealPayload(BaseModel):
    target_agent_id: str
    intro_message: str


class DealInitiatedPayload(BaseModel):
    deal_id: str
    vc_agent_id: str
    vc_profile: dict
    intro_message: str


class PitchPayload(BaseModel):
    deal_id: str
    elevator_pitch: str
    key_metrics: dict
    funding_ask: int
    use_of_funds: str
    competitive_advantage: str


class QuestionPayload(BaseModel):
    deal_id: str
    questions: list[str]


class AnswerPayload(BaseModel):
    deal_id: str
    answers: list[dict]


class DecisionPayload(BaseModel):
    deal_id: str
    decision: str  # "interest" or "pass"
    reasoning: str
    next_steps: str | None = None


class DealUpdatePayload(BaseModel):
    deal_id: str
    status: str
    message: str
    from_agent_id: str


class ErrorPayload(BaseModel):
    code: str
    message: str
