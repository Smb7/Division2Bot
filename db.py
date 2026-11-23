"""SQLite storage. Paths come from code, queries are parameterized."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from division2bot.snapshot import MissionLoot, Snapshot
from division2bot.watch import WATCH_LIMIT, Watch

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
_CREATE_GUILD_CONFIG = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id TEXT PRIMARY KEY,
    escalation_channel_id TEXT
)
"""
_CREATE_WATCHES = """
CREATE TABLE IF NOT EXISTS watches (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('brand', 'gear_set', 'slot', 'weapon')),
    name TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, kind, name)
)
"""
_CREATE_DELIVERIES = """
CREATE TABLE IF NOT EXISTS deliveries (
    guild_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, signature)
)
"""


async def open_db(path: Path | None = None) -> aiosqlite.Connection:
    db_path = path or DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(db_path)
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.execute(_CREATE_SNAPSHOTS)
    await connection.execute(_CREATE_GUILD_CONFIG)
    await connection.execute(_CREATE_WATCHES)
    await connection.execute(_CREATE_DELIVERIES)
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
    await connection.execute(
        "DELETE FROM deliveries WHERE signature LIKE ?", (f"{snapshot.date}|%",)
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


async def set_channel(
    connection: aiosqlite.Connection, guild_id: int, channel_id: int | None
) -> None:
    if channel_id is None:
        await connection.execute("DELETE FROM guild_config WHERE guild_id = ?", (str(guild_id),))
    else:
        await connection.execute(
            """
            INSERT INTO guild_config (guild_id, escalation_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                escalation_channel_id = excluded.escalation_channel_id
            """,
            (str(guild_id), str(channel_id)),
        )
    await connection.commit()


async def configured_channels(connection: aiosqlite.Connection) -> tuple[tuple[int, int], ...]:
    cursor = await connection.execute(
        """
        SELECT guild_id, escalation_channel_id
        FROM guild_config
        WHERE escalation_channel_id IS NOT NULL
        """
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple((int(guild_id), int(channel_id)) for guild_id, channel_id in rows)


async def channel_for_guild(connection: aiosqlite.Connection, guild_id: int) -> int | None:
    cursor = await connection.execute(
        "SELECT escalation_channel_id FROM guild_config WHERE guild_id = ?",
        (str(guild_id),),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None or row[0] is None:
        return None
    return int(row[0])


async def add_watch(connection: aiosqlite.Connection, watch: Watch) -> str:
    """Return ``added``, ``duplicate``, or ``limit``."""
    cursor = await connection.execute(
        "SELECT COUNT(*) FROM watches WHERE guild_id = ? AND user_id = ?",
        (str(watch.guild_id), str(watch.user_id)),
    )
    row = await cursor.fetchone()
    await cursor.close()
    count = int(row[0]) if row else 0
    if count >= WATCH_LIMIT:
        existing = await connection.execute(
            """
            SELECT 1 FROM watches
            WHERE guild_id = ? AND user_id = ? AND kind = ? AND name = ?
            """,
            (str(watch.guild_id), str(watch.user_id), watch.kind, watch.name),
        )
        duplicate = await existing.fetchone()
        await existing.close()
        if duplicate is None:
            return "limit"
    await connection.execute(
        """
        INSERT INTO watches (guild_id, user_id, kind, name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        (str(watch.guild_id), str(watch.user_id), watch.kind, watch.name),
    )
    cursor = await connection.execute("SELECT changes()")
    changed = await cursor.fetchone()
    await cursor.close()
    await connection.commit()
    if changed and int(changed[0]) == 0:
        return "duplicate"
    return "added"


async def remove_watch(connection: aiosqlite.Connection, watch: Watch) -> bool:
    cursor = await connection.execute(
        """
        DELETE FROM watches
        WHERE guild_id = ? AND user_id = ? AND kind = ? AND name = ?
        """,
        (str(watch.guild_id), str(watch.user_id), watch.kind, watch.name),
    )
    await connection.commit()
    removed = cursor.rowcount > 0
    await cursor.close()
    return removed


async def list_watches(
    connection: aiosqlite.Connection, guild_id: int, user_id: int
) -> tuple[Watch, ...]:
    cursor = await connection.execute(
        """
        SELECT guild_id, user_id, kind, name
        FROM watches
        WHERE guild_id = ? AND user_id = ?
        ORDER BY kind, name
        """,
        (str(guild_id), str(user_id)),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple(_watch_row(row) for row in rows)


async def watches_for_guild(connection: aiosqlite.Connection, guild_id: int) -> tuple[Watch, ...]:
    cursor = await connection.execute(
        """
        SELECT guild_id, user_id, kind, name
        FROM watches
        WHERE guild_id = ?
        ORDER BY user_id, kind, name
        """,
        (str(guild_id),),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple(_watch_row(row) for row in rows)


async def clear_watches(connection: aiosqlite.Connection, guild_id: int, user_id: int) -> None:
    await connection.execute(
        "DELETE FROM watches WHERE guild_id = ? AND user_id = ?",
        (str(guild_id), str(user_id)),
    )
    await connection.commit()


async def last_delivery_signature(connection: aiosqlite.Connection, guild_id: int) -> str | None:
    cursor = await connection.execute(
        """
        SELECT signature FROM deliveries
        WHERE guild_id = ?
        ORDER BY posted_at DESC
        LIMIT 1
        """,
        (str(guild_id),),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    return str(row[0])


async def record_delivery(
    connection: aiosqlite.Connection, guild_id: int, signature: str, posted_at: str
) -> None:
    await connection.execute(
        """
        INSERT INTO deliveries (guild_id, signature, posted_at)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, signature) DO UPDATE SET posted_at = excluded.posted_at
        """,
        (str(guild_id), signature, posted_at),
    )
    await connection.commit()


def _watch_row(row: tuple[object, ...]) -> Watch:
    return Watch(
        guild_id=int(str(row[0])),
        user_id=int(str(row[1])),
        kind=str(row[2]),
        name=str(row[3]),
    )
