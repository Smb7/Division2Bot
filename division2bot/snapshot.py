"""Parse the ProtoTrack Escalation text feed. No network and no Discord."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

FEED_URL = "https://prototrack.gg/target-loot/target-loot-current.txt"
MAX_FEED_CHARS = 20_000
FIELD_NAME_LIMIT = 100

_DATE = re.compile(r"^Date: (\d{4}-\d{2}-\d{2})$")
_MISSION = re.compile(r"^- ([^:]+): (.+)$")
_WEAPONS = re.compile(r"^- Weapons: (.+)$")
_GEAR = re.compile(r"^- Gear: (.+)$")
_UPDATED = re.compile(r"^Last updated: (.+)$")
_SOURCE = re.compile(r"^Source: (.+)$")


@dataclass(frozen=True)
class MissionLoot:
    mission: str
    loot: str


@dataclass(frozen=True)
class Snapshot:
    date: str
    rotation: str
    missions: tuple[MissionLoot, ...]
    weapon_cache: str
    gear_cache: str
    updated: str
    source: str
    raw: str

    def signature(self) -> tuple[object, ...]:
        """Date, mission list, and vendor lines. That is what makes a new post."""
        return (
            self.date,
            self.missions,
            self.weapon_cache,
            self.gear_cache,
        )


def parse_target_loot(text: str) -> Snapshot | None:
    """Return a snapshot, or None if the text is not the expected shape.

    A bad or partial feed is not turned into a guessed rotation.
    """
    if not text or len(text) > MAX_FEED_CHARS or "\x00" in text:
        return None
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]
    return _parse_blocks(normalized, _strip_edges(lines))


def _parse_blocks(text: str, lines: list[str]) -> Snapshot | None:
    """Parse the observed text shape. Extra or missing lines are rejected."""
    if len(lines) != 17:
        return None
    if lines[0] != "Daily Escalation Target Loot":
        return None
    date_match = _DATE.fullmatch(lines[1])
    if date_match is None or not lines[2].startswith("Rotation: "):
        return None
    try:
        datetime.strptime(date_match.group(1), "%Y-%m-%d")
    except ValueError:
        return None
    rotation = lines[2].removeprefix("Rotation: ").strip()
    if not rotation or lines[3] != "" or lines[4] != "Missions:":
        return None
    missions: list[MissionLoot] = []
    for line in lines[5:10]:
        match = _MISSION.fullmatch(line)
        if match is None:
            return None
        mission = match.group(1).strip()
        loot = match.group(2).strip()
        if not _plain_label(mission) or not _plain_label(loot):
            return None
        missions.append(MissionLoot(mission=mission, loot=loot))
    if lines[10] != "" or lines[11] != "Vendor Caches:":
        return None
    weapons = _WEAPONS.fullmatch(lines[12])
    gear = _GEAR.fullmatch(lines[13])
    if weapons is None or gear is None or lines[14] != "":
        return None
    updated = _UPDATED.fullmatch(lines[15])
    source = _SOURCE.fullmatch(lines[16])
    if updated is None or source is None:
        return None
    weapon_cache = weapons.group(1).strip()
    gear_cache = gear.group(1).strip()
    updated_text = updated.group(1).strip()
    source_text = source.group(1).strip()
    if not all(
        _plain_label(value) for value in (weapon_cache, gear_cache, updated_text, source_text)
    ):
        return None
    return Snapshot(
        date=date_match.group(1),
        rotation=rotation,
        missions=tuple(missions),
        weapon_cache=weapon_cache,
        gear_cache=gear_cache,
        updated=updated_text,
        source=source_text,
        raw=text if text.endswith("\n") else f"{text}\n",
    )


def snapshot_changed(previous: Snapshot | None, current: Snapshot) -> bool:
    if previous is None:
        return True
    return previous.signature() != current.signature()


def loot_date(now: datetime) -> str:
    """Calendar date of the loot day. The reset is 08:00 UTC."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    utc = now.astimezone(UTC)
    if utc.hour < 8:
        utc -= timedelta(days=1)
    return utc.date().isoformat()


def next_daily_reset(loot_day: str) -> datetime:
    day = datetime.strptime(loot_day, "%Y-%m-%d").replace(tzinfo=UTC)
    return day.replace(hour=8) + timedelta(days=1)


def render_snapshot_text(snapshot: Snapshot) -> str:
    """Canonical text an admin override can be parsed back from."""
    mission_lines = [f"- {item.mission}: {item.loot}" for item in snapshot.missions]
    lines = [
        "Daily Escalation Target Loot",
        f"Date: {snapshot.date}",
        f"Rotation: {snapshot.rotation}",
        "",
        "Missions:",
        *mission_lines,
        "",
        "Vendor Caches:",
        f"- Weapons: {snapshot.weapon_cache}",
        f"- Gear: {snapshot.gear_cache}",
        "",
        f"Last updated: {snapshot.updated}",
        f"Source: {snapshot.source}",
    ]
    return "\n".join(lines) + "\n"


def override_snapshot(
    *,
    date: str,
    missions: tuple[MissionLoot, ...],
    weapon_cache: str,
    gear_cache: str,
    updated: str,
) -> Snapshot | None:
    draft = Snapshot(
        date=date,
        rotation="Admin override",
        missions=missions,
        weapon_cache=weapon_cache,
        gear_cache=gear_cache,
        updated=updated,
        source="admin override",
        raw="",
    )
    text = render_snapshot_text(draft)
    return parse_target_loot(text)


def _strip_edges(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and lines[start] == "":
        start += 1
    while end > start and lines[end - 1] == "":
        end -= 1
    return lines[start:end]


def _plain_label(value: str) -> bool:
    if not value or len(value) > FIELD_NAME_LIMIT:
        return False
    return all(char.isprintable() and char not in "\r\n\t" for char in value)
