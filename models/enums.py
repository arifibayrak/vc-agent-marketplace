from enum import Enum


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


class MessageType(str, Enum):
    REGISTER = "register"
    REGISTER_ACK = "register_ack"
    DISCOVER = "discover"
    DISCOVER_RESULTS = "discover_results"
    INITIATE_DEAL = "initiate_deal"
    DEAL_INITIATED = "deal_initiated"
    PITCH = "pitch"
    QUESTION = "question"
    ANSWER = "answer"
    INTEREST = "interest"
    PASS = "pass"
    DEAL_UPDATE = "deal_update"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
