#!/usr/bin/env node
/**
 * Minimal example: connect an external startup agent to the marketplace.
 *
 * Usage:
 *   npm install ws
 *   python run_server.py           # in one terminal
 *   node examples/node_client.js   # in another terminal
 */

const WebSocket = require("ws");

const MARKETPLACE_URL = "ws://localhost:8000/ws/agent";

const PROFILE = {
  name: "NodeBot",
  sector: "saas",
  stage: "seed",
  funding_ask: 1500000,
  elevator_pitch: "We automate customer onboarding with conversational AI.",
  metrics: { mrr: 20000, growth_rate: 0.3, customers: 15 },
  team_size: 4,
  founded_year: 2025,
  location: "Berlin, Germany",
};

const ws = new WebSocket(MARKETPLACE_URL);
let agentId = null;

ws.on("open", () => {
  ws.send(
    JSON.stringify({
      message_type: "register",
      sender_id: "pending",
      payload: { agent_type: "startup", profile: PROFILE },
    })
  );
  console.log("Connecting to marketplace...");
});

ws.on("message", (data) => {
  const msg = JSON.parse(data);
  const type = msg.message_type;
  const payload = msg.payload || {};

  if (type === "register_ack") {
    agentId = payload.agent_id;
    console.log(`Registered as: ${agentId}`);
  } else if (type === "deal_initiated") {
    const dealId = payload.deal_id;
    const vcName = (payload.vc_profile || {}).name || "A VC";
    console.log(`Deal from ${vcName} (${dealId})`);

    ws.send(
      JSON.stringify({
        message_type: "pitch",
        sender_id: agentId,
        payload: {
          deal_id: dealId,
          elevator_pitch: PROFILE.elevator_pitch,
          key_metrics: PROFILE.metrics,
          funding_ask: PROFILE.funding_ask,
          use_of_funds: "Product and growth",
          competitive_advantage: "Best onboarding NPS in the market",
        },
      })
    );
    console.log(`  Sent pitch for ${dealId}`);
  } else if (type === "question") {
    const dealId = payload.deal_id;
    const questions = payload.questions || [];
    console.log(`Got ${questions.length} questions for ${dealId}`);

    const answers = questions.map((q) => ({
      question: q,
      answer: `Regarding "${q}": here is our detailed response...`,
    }));

    ws.send(
      JSON.stringify({
        message_type: "answer",
        sender_id: agentId,
        payload: { deal_id: dealId, answers },
      })
    );
    console.log(`  Sent answers for ${dealId}`);
  } else if (type === "deal_update") {
    console.log(`Decision: ${payload.status} - ${(payload.message || "").slice(0, 100)}`);
  } else if (type === "heartbeat") {
    // keepalive
  } else {
    console.log(`Unknown message: ${type}`);
  }
});

ws.on("close", () => console.log("Disconnected"));
ws.on("error", (err) => console.error("Error:", err.message));
