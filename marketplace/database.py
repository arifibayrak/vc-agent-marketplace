import json
from datetime import datetime, timezone

import aiosqlite

DB_PATH = "marketplace.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                agent_type TEXT NOT NULL,
                name TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                registered_at TEXT NOT NULL,
                last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS deals (
                id TEXT PRIMARY KEY,
                vc_agent_id TEXT NOT NULL,
                startup_agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                match_score REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                outcome TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                deal_id TEXT,
                message_type TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                recipient_id TEXT,
                payload_json TEXT NOT NULL,
                correlation_id TEXT,
                created_at TEXT NOT NULL
            );
        """)
        await db.commit()


async def save_agent(agent_id: str, agent_type: str, name: str, profile: dict):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO agents (id, agent_type, name, profile_json, registered_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, agent_type, name, json.dumps(profile), now, now),
        )
        await db.commit()


async def save_deal(deal_id: str, vc_agent_id: str, startup_agent_id: str, status: str, match_score: float):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO deals (id, vc_agent_id, startup_agent_id, status, match_score, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (deal_id, vc_agent_id, startup_agent_id, status, match_score, now, now),
        )
        await db.commit()


async def update_deal_status(deal_id: str, status: str, outcome: str | None = None):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        if outcome:
            await db.execute(
                "UPDATE deals SET status = ?, outcome = ?, updated_at = ? WHERE id = ?",
                (status, outcome, now, deal_id),
            )
        else:
            await db.execute(
                "UPDATE deals SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, deal_id),
            )
        await db.commit()


async def save_message(message_id: str, deal_id: str | None, message_type: str,
                       sender_id: str, recipient_id: str | None, payload: dict,
                       correlation_id: str | None):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (id, deal_id, message_type, sender_id, recipient_id, payload_json, correlation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, deal_id, message_type, sender_id, recipient_id, json.dumps(payload), correlation_id, now),
        )
        await db.commit()


async def get_all_agents() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM agents WHERE status = 'active' ORDER BY registered_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_deals() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deals ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_deal_messages(deal_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM messages WHERE deal_id = ? ORDER BY created_at",
            (deal_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
