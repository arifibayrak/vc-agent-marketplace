from pydantic import BaseModel

from models.enums import AgentType, FundingStage, Sector


class StartupProfile(BaseModel):
    name: str
    sector: Sector
    stage: FundingStage
    funding_ask: int
    elevator_pitch: str
    metrics: dict
    team_size: int
    founded_year: int
    location: str


class VCProfile(BaseModel):
    name: str
    firm_name: str
    target_sectors: list[Sector]
    target_stages: list[FundingStage]
    check_size_min: int
    check_size_max: int
    portfolio_focus: str
    deals_per_year: int


class AgentRegistration(BaseModel):
    agent_type: AgentType
    profile: StartupProfile | VCProfile
