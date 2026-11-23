import asyncio
from datetime import UTC, datetime
from pathlib import Path

import discord
import pytest

from cogs.escalation import can_configure
from db import get_snapshot, open_db, save_feed_snapshot, save_override
from division2bot.snapshot import (
    FEED_URL,
    loot_date,
    override_snapshot,
    parse_target_loot,
    snapshot_changed,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_current_fixture() -> None:
    snapshot = parse_target_loot(_read("target-loot-current.txt"))
    assert snapshot is not None
    assert snapshot.date == "2026-11-22"
    assert len(snapshot.missions) == 5
    assert snapshot.missions[0].mission == "The Art Museum"
    assert snapshot.missions[0].loot == "Umbra Initiative"
    assert snapshot.missions[4].loot == "Grupo Sombra S.A."
    assert snapshot.weapon_cache == "Assault Rifles"
    assert snapshot.gear_cache == "Masks"
    assert snapshot.source == "ProtoTrack.gg"


def test_changed_mission_list_should_post() -> None:
    current = parse_target_loot(_read("target-loot-current.txt"))
    nxt = parse_target_loot(_read("target-loot-next.txt"))
    assert current is not None and nxt is not None
    assert snapshot_changed(None, current)
    assert snapshot_changed(current, nxt)
    assert not snapshot_changed(current, current)
    vendor_only = parse_target_loot(
        _read("target-loot-current.txt").replace("- Gear: Masks", "- Gear: Holsters")
    )
    assert vendor_only is not None
    assert snapshot_changed(current, vendor_only)


def test_bad_feed_is_not_a_rotation() -> None:
    assert parse_target_loot("") is None
    assert parse_target_loot("<html>not a rotation</html>") is None
    broken = _read("target-loot-current.txt").replace("- Lincoln Memorial: Electrique\n", "")
    assert parse_target_loot(broken) is None
    invalid_day = _read("target-loot-current.txt").replace("Date: 2026-11-22", "Date: 2026-13-22")
    assert parse_target_loot(invalid_day) is None


def test_loot_date_uses_0800_utc() -> None:
    assert loot_date(datetime(2026, 11, 22, 8, 0, tzinfo=UTC)) == "2026-11-22"
    assert loot_date(datetime(2026, 11, 22, 7, 59, tzinfo=UTC)) == "2026-11-21"
    with pytest.raises(ValueError, match="timezone-aware"):
        loot_date(datetime(2026, 11, 22, 9, 0))


def test_feed_url_is_https_and_fixed() -> None:
    assert FEED_URL == "https://prototrack.gg/target-loot/target-loot-current.txt"


def test_override_round_trips_and_blocks_the_feed(tmp_path: Path) -> None:
    asyncio.run(_override_round_trip(tmp_path))


async def _override_round_trip(tmp_path: Path) -> None:
    current = parse_target_loot(_read("target-loot-current.txt"))
    assert current is not None
    hostile = "'; DROP TABLE snapshots; --"
    override = override_snapshot(
        date=current.date,
        missions=(
            current.missions[0],
            current.missions[1],
            current.missions[2],
            current.missions[3],
            type(current.missions[4])(current.missions[4].mission, hostile),
        ),
        weapon_cache=current.weapon_cache,
        gear_cache=current.gear_cache,
        updated="admin",
    )
    assert override is not None
    assert override.source == "admin override"
    connection = await open_db(tmp_path / "bot.sqlite")
    try:
        await save_feed_snapshot(connection, current)
        await save_override(connection, override)
        await save_feed_snapshot(connection, current)
        stored = await get_snapshot(connection, current.date)
        assert stored is not None
        snapshot, source = stored
        assert source == "override"
        assert snapshot.missions[4].loot == hostile
        cursor = await connection.execute("SELECT COUNT(*) FROM snapshots")
        row = await cursor.fetchone()
        await cursor.close()
        assert row == (1,)
    finally:
        await connection.close()


def test_configure_permission_is_not_a_role_name() -> None:
    assert can_configure(discord.Permissions(manage_channels=True))
    assert can_configure(discord.Permissions(administrator=True))
    assert not can_configure(discord.Permissions(send_messages=True))
