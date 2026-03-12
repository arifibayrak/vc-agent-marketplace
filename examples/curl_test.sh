#!/bin/bash
# Quick test: register an agent using websocat (install: cargo install websocat)
#
# Usage:
#   python run_server.py         # start marketplace first
#   bash examples/curl_test.sh   # run this script

echo "Connecting to marketplace and registering a test agent..."
echo "Press Ctrl+C to disconnect."
echo ""

# Send register message, then listen for responses
(
  echo '{"message_type":"register","sender_id":"pending","payload":{"agent_type":"startup","profile":{"name":"TestBot","sector":"ai_ml","stage":"seed","funding_ask":1000000,"elevator_pitch":"A quick test agent.","metrics":{"mrr":10000,"growth_rate":0.1,"customers":5},"team_size":3,"founded_year":2025,"location":"Test"}}}'
  # Keep connection open
  while true; do
    sleep 20
    echo '{"message_type":"heartbeat"}'
  done
) | websocat ws://localhost:8000/ws/agent

# Alternative using python one-liner if websocat is not available:
# python3 -c "
# import asyncio, json, websockets
# async def t():
#     async with websockets.connect('ws://localhost:8000/ws/agent') as ws:
#         await ws.send(json.dumps({'message_type':'register','sender_id':'pending','payload':{'agent_type':'startup','profile':{'name':'TestBot','sector':'ai_ml','stage':'seed','funding_ask':1000000,'elevator_pitch':'Test','metrics':{'mrr':10000,'growth_rate':0.1,'customers':5},'team_size':3,'founded_year':2025,'location':'Test'}}}))
#         print(await ws.recv())
# asyncio.run(t())
# "
