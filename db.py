"""SQLite storage. Paths come from code, queries are parameterized."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from division2bot.snapshot import MissionLoot, Snapshot

ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "division2bot.sqlite"

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS snapshots (
    date TEXT PRIMARY KEY,
    raw_text TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('feed', 'override')),
    posted_at TEXT
)
"""


async def open_db(path: Path | None = None) -> aiosqlite.Connection:
    db_path = path or DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(db_path)
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.execute(_CREATE_SNAPSHOTS)
    await connection.commit()
    return connection


async def get_snapshot(connection: aiosqlite.Connection, date: str) -> tuple[Snapshot, str] | None:
    cursor = await connection.execute(
        "SELECT raw_text, parsed_json, source FROM snapshots WHERE date = ?",
        (date,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    raw_text, parsed_json, source = row
    return _snapshot_from_json(str(parsed_json), str(raw_text)), str(source)


async def save_feed_snapshot(connection: aiosqlite.Connection, snapshot: Snapshot) -> None:
    """Store a feed snapshot. An admin override for that date is left alone."""
    await connection.execute(
        """
        INSERT INTO snapshots (date, raw_text, parsed_json, source, posted_at)
        VALUES (?, ?, ?, 'feed', NULL)
        ON CONFLICT(date) DO UPDATE SET
            raw_text = excluded.raw_text,
            parsed_json = excluded.parsed_json,
            source = 'feed'
        WHERE snapshots.source != 'override'
        """,
        (snapshot.date, snapshot.raw, _dump(snapshot)),
    )
    await connection.commit()


async def save_override(connection: aiosqlite.Connection, snapshot: Snapshot) -> None:
    """Store an admin override. Later feed polls must not replace this date."""
    await connection.execute(
        """
        INSERT INTO snapshots (date, raw_text, parsed_json, source, posted_at)
        VALUES (?, ?, ?, 'override', NULL)
        ON CONFLICT(date) DO UPDATE SET
            raw_text = excluded.raw_text,
            parsed_json = excluded.parsed_json,
            source = 'override',
            posted_at = NULL
        """,
        (snapshot.date, snapshot.raw, _dump(snapshot)),
    )
    await connection.commit()


def _dump(snapshot: Snapshot) -> str:
    payload = {
        "date": snapshot.date,
        "rotation": snapshot.rotation,
        "missions": [{"mission": item.mission, "loot": item.loot} for item in snapshot.missions],
        "weapon_cache": snapshot.weapon_cache,
        "gear_cache": snapshot.gear_cache,
        "updated": snapshot.updated,
        "source": snapshot.source,
    }
    return json.dumps(payload, ensure_ascii=False)


def _snapshot_from_json(payload: str, raw: str) -> Snapshot:
    data = json.loads(payload)
    missions = tuple(
        MissionLoot(mission=str(item["mission"]), loot=str(item["loot"]))
        for item in data["missions"]
    )
    return Snapshot(
        date=str(data["date"]),
        rotation=str(data["rotation"]),
        missions=missions,
        weapon_cache=str(data["weapon_cache"]),
        gear_cache=str(data["gear_cache"]),
        updated=str(data["updated"]),
        source=str(data["source"]),
        raw=raw,
    )
