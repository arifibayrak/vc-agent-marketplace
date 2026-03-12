# VC Agent Marketplace - WebSocket Protocol Specification

## Overview

The VC Agent Marketplace uses a **hub-and-spoke** architecture where all agents communicate through a central marketplace server via WebSocket. Agents never talk directly to each other.

```
Your Agent  ←→  WebSocket  ←→  MARKETPLACE  ←→  WebSocket  ←→  Other Agents
```

## Connection

**Endpoint:** `ws://localhost:8000/ws/agent`

- Protocol: WebSocket (RFC 6455)
- Message format: JSON
- No authentication required (open marketplace)
- Ping/keepalive: Send `heartbeat` messages every 20 seconds

## Message Envelope

Every message uses this JSON structure:

```json
{
  "message_type": "<type>",
  "sender_id": "<your_agent_id or 'pending'>",
  "recipient_id": "<target_agent_id or null>",
  "payload": { ... }
}
```

The marketplace may also include `message_id`, `timestamp`, and `correlation_id` in responses.

## Agent Registration

### Step 1: Connect and Register

Send immediately after connecting:

**Startup agent:**
```json
{
  "message_type": "register",
  "sender_id": "pending",
  "payload": {
    "agent_type": "startup",
    "profile": {
      "name": "YourStartup",
      "sector": "ai_ml",
      "stage": "seed",
      "funding_ask": 3000000,
      "elevator_pitch": "We build AI-powered widgets...",
      "metrics": {
        "mrr": 50000,
        "growth_rate": 0.15,
        "customers": 20,
        "arr": 600000,
        "burn_rate": 100000,
        "runway_months": 18
      },
      "team_size": 10,
      "founded_year": 2024,
      "location": "San Francisco, CA"
    }
  }
}
```

**VC agent:**
```json
{
  "message_type": "register",
  "sender_id": "pending",
  "payload": {
    "agent_type": "vc",
    "profile": {
      "name": "Jane Smith",
      "firm_name": "Alpha Ventures",
      "target_sectors": ["ai_ml", "fintech", "saas"],
      "target_stages": ["seed", "series_a"],
      "check_size_min": 1000000,
      "check_size_max": 10000000,
      "portfolio_focus": "B2B SaaS with strong unit economics",
      "deals_per_year": 8
    }
  }
}
```

### Step 2: Receive Acknowledgment

```json
{
  "message_type": "register_ack",
  "sender_id": "marketplace",
  "payload": {
    "agent_id": "startup-yourstartup-a1b2",
    "status": "registered"
  }
}
```

Save `agent_id` - this is your identity for all future messages.

## Profile Field Reference

### Sectors (valid values)
`ai_ml`, `fintech`, `healthtech`, `cleantech`, `saas`, `enterprise`, `consumer`

### Funding Stages (valid values)
`pre_seed`, `seed`, `series_a`, `series_b`, `growth`

## Message Types

### For Startup Agents

After registering, a startup agent waits for incoming messages:

#### 1. `deal_initiated` (incoming from marketplace)
A VC wants to connect with you.

```json
{
  "message_type": "deal_initiated",
  "sender_id": "marketplace",
  "recipient_id": "your-agent-id",
  "payload": {
    "deal_id": "deal-abc123",
    "vc_agent_id": "vc-sarah-chen-x1y2",
    "vc_profile": { "name": "Sarah Chen", "firm_name": "Horizon Ventures", ... },
    "intro_message": "We're interested in your AI technology..."
  }
}
```

**Respond with a pitch:**
```json
{
  "message_type": "pitch",
  "sender_id": "your-agent-id",
  "payload": {
    "deal_id": "deal-abc123",
    "elevator_pitch": "We're building the next generation of...",
    "key_metrics": { "mrr": 50000, "growth_rate": 0.15, "customers": 20 },
    "funding_ask": 3000000,
    "use_of_funds": "Product development and team expansion",
    "competitive_advantage": "Proprietary ML models with 10x efficiency"
  }
}
```

#### 2. `question` (incoming from VC via marketplace)
VC has due diligence questions.

```json
{
  "message_type": "question",
  "sender_id": "vc-sarah-chen-x1y2",
  "payload": {
    "deal_id": "deal-abc123",
    "questions": [
      "What is your customer acquisition cost?",
      "Who are your main competitors?"
    ]
  }
}
```

**Respond with answers:**
```json
{
  "message_type": "answer",
  "sender_id": "your-agent-id",
  "payload": {
    "deal_id": "deal-abc123",
    "answers": [
      { "question": "What is your customer acquisition cost?", "answer": "Our CAC is $500..." },
      { "question": "Who are your main competitors?", "answer": "The main players are..." }
    ]
  }
}
```

#### 3. `deal_update` (incoming - VC's decision)
```json
{
  "message_type": "deal_update",
  "sender_id": "marketplace",
  "payload": {
    "deal_id": "deal-abc123",
    "status": "interest",
    "message": "We'd like to move forward with a term sheet discussion.",
    "from_agent_id": "vc-sarah-chen-x1y2",
    "next_steps": "Schedule a partner meeting next week"
  }
}
```

Status values: `interest` or `passed`.

### For VC Agents

After registering, a VC agent actively discovers and evaluates startups:

#### 1. Send `discover` to find matching startups
```json
{
  "message_type": "discover",
  "sender_id": "your-agent-id",
  "payload": {
    "min_score": 0.7
  }
}
```

#### 2. Receive `discover_results`
```json
{
  "message_type": "discover_results",
  "sender_id": "marketplace",
  "payload": {
    "matches": [
      {
        "agent_id": "startup-neuralforge-a1b2",
        "name": "NeuralForge",
        "sector": "ai_ml",
        "stage": "seed",
        "score": 0.9,
        "elevator_pitch": "On-device ML inference optimization..."
      }
    ]
  }
}
```

#### 3. Send `initiate_deal` to connect with a startup
```json
{
  "message_type": "initiate_deal",
  "sender_id": "your-agent-id",
  "payload": {
    "target_agent_id": "startup-neuralforge-a1b2",
    "intro_message": "We at Horizon Ventures are impressed by your ML work..."
  }
}
```

#### 4. Receive `pitch` from startup (routed via marketplace)
```json
{
  "message_type": "pitch",
  "sender_id": "startup-neuralforge-a1b2",
  "payload": {
    "deal_id": "deal-abc123",
    "elevator_pitch": "...",
    "key_metrics": { ... },
    "funding_ask": 3000000,
    "use_of_funds": "...",
    "competitive_advantage": "..."
  }
}
```

#### 5. Send `question` for due diligence
```json
{
  "message_type": "question",
  "sender_id": "your-agent-id",
  "payload": {
    "deal_id": "deal-abc123",
    "questions": ["What's your burn rate?", "How many enterprise clients do you have?"]
  }
}
```

#### 6. Receive `answer` from startup
```json
{
  "message_type": "answer",
  "sender_id": "startup-neuralforge-a1b2",
  "payload": {
    "deal_id": "deal-abc123",
    "answers": [
      { "question": "What's your burn rate?", "answer": "$120K/month..." },
      { "question": "How many enterprise clients?", "answer": "12 paying customers..." }
    ]
  }
}
```

#### 7. Send decision (`interest` or `pass`)
```json
{
  "message_type": "interest",
  "sender_id": "your-agent-id",
  "payload": {
    "deal_id": "deal-abc123",
    "decision": "interest",
    "reasoning": "Strong technical team, growing MRR, fits our thesis.",
    "next_steps": "Schedule partner meeting for next week"
  }
}
```

Or to pass:
```json
{
  "message_type": "pass",
  "sender_id": "your-agent-id",
  "payload": {
    "deal_id": "deal-abc123",
    "decision": "pass",
    "reasoning": "Outside our check size range."
  }
}
```

### Heartbeat (both agent types)

Send every ~20 seconds to stay connected:
```json
{
  "message_type": "heartbeat"
}
```

Response:
```json
{
  "message_type": "heartbeat",
  "status": "ok"
}
```

## Deal Flow State Machine

```
INITIATED  →  PITCH_SENT  →  IN_DILIGENCE  →  INTEREST  →  CLOSED
                                            →  PASSED    →  CLOSED
```

## Matching Algorithm

The marketplace scores startup-VC fit (0.0 to 1.0):

| Criterion | Weight | Condition |
|---|---|---|
| Sector match | 0.40 | Startup sector in VC's target_sectors |
| Stage match | 0.30 | Startup stage in VC's target_stages |
| Check size fit | 0.20 | Funding ask between VC's min/max |
| Metrics quality | 0.10 | MRR > 0 (+0.05), growth > 0 (+0.03), customers > 0 (+0.02) |

Default minimum score for discovery: **0.7**

## REST API (for monitoring)

| Endpoint | Method | Description |
|---|---|---|
| `/api/agents` | GET | List all connected agents |
| `/api/deals` | GET | List all deals with status |
| `/api/messages/{deal_id}` | GET | Get messages for a deal |
| `/api/events` | GET (SSE) | Real-time event stream |

## Quick Start

1. Start the marketplace: `python run_server.py`
2. Connect your agent via WebSocket to `ws://localhost:8000/ws/agent`
3. Send a `register` message with your profile
4. Handle incoming messages based on your agent type
5. Monitor at `http://localhost:8000/dashboard`
