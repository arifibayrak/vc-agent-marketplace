// VC Agent Marketplace - Dashboard
// Connects to SSE endpoint and REST API for real-time updates

const API_BASE = '';

// State
const agents = new Map();
const deals = new Map();

// DOM elements
const agentsList = document.getElementById('agents-list');
const dealsList = document.getElementById('deals-list');
const eventsList = document.getElementById('events-list');
const connectionStatus = document.getElementById('connection-status');

// --- SSE Connection ---

function connectSSE() {
    const evtSource = new EventSource(`${API_BASE}/api/events`);

    evtSource.onopen = () => {
        connectionStatus.textContent = 'Connected';
        connectionStatus.className = 'status-indicator connected';
    };

    evtSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleEvent(data);
        } catch (e) {
            console.error('Failed to parse event:', e);
        }
    };

    evtSource.onerror = () => {
        connectionStatus.textContent = 'Disconnected';
        connectionStatus.className = 'status-indicator disconnected';
        evtSource.close();
        // Reconnect after 3 seconds
        setTimeout(connectSSE, 3000);
    };
}

// --- Event Handling ---

function handleEvent(event) {
    // Add to event log
    addEventToLog(event);

    // Refresh agents and deals
    fetchAgents();
    fetchDeals();
}

function addEventToLog(event) {
    const data = event.data || {};
    const source = data.source || 'SYSTEM';
    const message = data.message || JSON.stringify(data);
    const timestamp = event.timestamp ? new Date(event.timestamp) : new Date();
    const timeStr = timestamp.toLocaleTimeString('en-US', { hour12: false });

    const div = document.createElement('div');
    div.className = 'event-item';
    div.innerHTML = `
        <span class="event-time">${timeStr}</span>
        <span class="event-source ${source}">${source}</span>
        <span class="event-message">${escapeHtml(message)}</span>
    `;

    eventsList.appendChild(div);
    eventsList.scrollTop = eventsList.scrollHeight;
}

// --- REST API ---

async function fetchAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/agents`);
        const data = await res.json();
        renderAgents(data);
    } catch (e) { /* ignore */ }
}

async function fetchDeals() {
    try {
        const res = await fetch(`${API_BASE}/api/deals`);
        const data = await res.json();
        renderDeals(data);
    } catch (e) { /* ignore */ }
}

// --- Rendering ---

function renderAgents(agentList) {
    agentsList.innerHTML = '';
    for (const agent of agentList) {
        const profile = agent.profile || {};
        const isStartup = agent.agent_type === 'startup';
        const detail = isStartup
            ? `${profile.sector || ''} | ${profile.stage || ''} | $${((profile.funding_ask || 0) / 1e6).toFixed(1)}M`
            : `${(profile.target_sectors || []).join(', ')} | $${((profile.check_size_min || 0) / 1e6).toFixed(0)}-${((profile.check_size_max || 0) / 1e6).toFixed(0)}M`;

        const card = document.createElement('div');
        card.className = 'agent-card';
        card.innerHTML = `
            <div class="agent-name">${escapeHtml(agent.name)}</div>
            <span class="agent-type ${agent.agent_type}">${agent.agent_type.toUpperCase()}</span>
            <div class="agent-detail">${escapeHtml(detail)}</div>
        `;
        agentsList.appendChild(card);
    }
}

function renderDeals(dealList) {
    dealsList.innerHTML = '';
    if (dealList.length === 0) {
        dealsList.innerHTML = '<p style="color: #484f58; font-size: 0.85rem; text-align: center; padding: 2rem;">Waiting for deals...</p>';
        return;
    }
    for (const deal of dealList) {
        const card = document.createElement('div');
        card.className = 'deal-card';
        card.innerHTML = `
            <div class="deal-header">
                <span class="deal-parties">${escapeHtml(deal.vc_name)} &harr; ${escapeHtml(deal.startup_name)}</span>
                <span class="deal-score">Score: ${(deal.match_score * 100).toFixed(0)}%</span>
            </div>
            <span class="deal-status ${deal.status}">${deal.status.replace('_', ' ').toUpperCase()}</span>
            ${deal.outcome ? `<div class="deal-outcome">${escapeHtml(deal.outcome.substring(0, 120))}</div>` : ''}
        `;
        dealsList.appendChild(card);
    }
}

// --- Utilities ---

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// --- Init ---

connectSSE();
fetchAgents();
fetchDeals();

// Periodic refresh as backup
setInterval(() => {
    fetchAgents();
    fetchDeals();
}, 5000);
