"""A2A protocol types and domain models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Domain Enums (reused from WebSocket version) ──────────────────────

class AgentType(str, Enum):
    STARTUP = "startup"
    VC = "vc"


class FundingStage(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    GROWTH = "growth"


class Sector(str, Enum):
    AI_ML = "ai_ml"
    FINTECH = "fintech"
    HEALTHTECH = "healthtech"
    CLEANTECH = "cleantech"
    SAAS = "saas"
    ENTERPRISE = "enterprise"
    CONSUMER = "consumer"


class DealStatus(str, Enum):
    INITIATED = "initiated"
    PITCH_SENT = "pitch_sent"
    IN_DILIGENCE = "in_diligence"
    INTEREST = "interest"
    PASSED = "passed"
    CLOSED = "closed"


# ── A2A Protocol Types ────────────────────────────────────────────────

class Skill(BaseModel):
    id: str
    name: str
    description: str


class Capabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: Capabilities = Field(default_factory=Capabilities)
    skills: list[Skill] = []
    defaultInputModes: list[str] = ["text"]
    defaultOutputModes: list[str] = ["text"]
    metadata: dict[str, Any] = {}


class Part(BaseModel):
    type: str  # "text" or "data"
    text: str | None = None
    data: dict[str, Any] | None = None


class Message(BaseModel):
    role: str  # "user" or "agent"
    parts: list[Part]


class TaskStatus(BaseModel):
    state: str  # submitted, working, completed, failed, canceled


class Artifact(BaseModel):
    parts: list[Part]


class TaskParams(BaseModel):
    id: str
    skill_id: str | None = None
    message: Message


class TaskResult(BaseModel):
    id: str
    status: TaskStatus
    artifacts: list[Artifact] = []


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    id: str
    params: TaskParams


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    result: TaskResult | None = None
    error: dict[str, Any] | None = None


# ── Deal Model ────────────────────────────────────────────────────────

class Deal(BaseModel):
    deal_id: str
    vc_agent_url: str
    startup_agent_url: str
    vc_name: str = ""
    startup_name: str = ""
    status: DealStatus = DealStatus.INITIATED
    match_score: float = 0.0
    outcome: str | None = None
