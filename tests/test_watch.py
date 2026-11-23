import asyncio
from datetime import UTC, datetime
from pathlib import Path

from cogs.escalation import Escalation
from db import last_delivery_signature, open_db, record_delivery, save_override
from division2bot.catalog import load_catalog
from division2bot.snapshot import override_snapshot, parse_target_loot
from division2bot.watch import (
    Watch,
    delivery_signature,
    matching_user_ids,
    mention_content,
    poll_interval_seconds,
    resolve_watch_name,
    should_deliver,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _current():
    snapshot = parse_target_loot((FIXTURES / "target-loot-current.txt").read_text(encoding="utf-8"))
    assert snapshot is not None
    return snapshot


def test_watch_hit_mentions_only_matching_users() -> None:
    snapshot = _current()
    watches = [
        Watch(1, 10, "brand", "Grupo Sombra S.A."),
        Watch(1, 11, "brand", "Providence Defense"),
        Watch(1, 12, "gear_set", "Umbra Initiative"),
        Watch(1, 13, "slot", "Masks"),
        Watch(1, 14, "slot", "Holsters"),
        Watch(1, 15, "weapon", "Assault Rifles"),
        Watch(1, 16, "weapon", "LMGs"),
    ]
    hits = matching_user_ids(snapshot, watches)
    assert hits == (10, 12, 13, 15)
    assert "10" in mention_content(hits)
    assert "11" not in mention_content(hits)


def test_post_once_when_the_signature_is_unchanged() -> None:
    current = _current()
    signature = delivery_signature(current)
    assert should_deliver(None, current)
    assert not should_deliver(signature, current)
    nxt = parse_target_loot((FIXTURES / "target-loot-next.txt").read_text(encoding="utf-8"))
    assert nxt is not None
    assert should_deliver(signature, nxt)
    assert poll_interval_seconds(8) == 600
    assert poll_interval_seconds(11) == 600
    assert poll_interval_seconds(12) == 3600
    assert poll_interval_seconds(7) == 3600


def test_watch_names_resolve_from_the_catalog() -> None:
    catalog = load_catalog()
    assert resolve_watch_name("brand", "grupo", catalog) == "Grupo Sombra S.A."
    assert resolve_watch_name("gear_set", "striker", catalog) == "Striker's Battlegear"
    assert resolve_watch_name("slot", "mask", catalog) == "Masks"
    assert resolve_watch_name("weapon", "lmg", catalog) == "LMGs"
    assert resolve_watch_name("brand", "a", catalog) is None
    assert resolve_watch_name("slot", "not-a-slot", catalog) is None


def test_recorded_delivery_stops_a_repost_and_override_clears_it(tmp_path: Path) -> None:
    asyncio.run(_delivery_round_trip(tmp_path))


async def _delivery_round_trip(tmp_path: Path) -> None:
    current = _current()
    connection = await open_db(tmp_path / "bot.sqlite")
    try:
        signature = delivery_signature(current)
        assert await last_delivery_signature(connection, 7) is None
        await record_delivery(connection, 7, signature, datetime.now(UTC).isoformat())
        assert await last_delivery_signature(connection, 7) == signature
        assert not should_deliver(await last_delivery_signature(connection, 7), current)
        override = override_snapshot(
            date=current.date,
            missions=current.missions,
            weapon_cache="LMGs",
            gear_cache=current.gear_cache,
            updated="admin",
        )
        assert override is not None
        await save_override(connection, override)
        assert await last_delivery_signature(connection, 7) is None
        assert should_deliver(None, override)
    finally:
        await connection.close()


def test_escalation_commands_include_channel_and_watch() -> None:
    names = {command.name for command in Escalation.__cog_app_commands__}
    assert {"today", "set", "channel", "watch"} <= names
