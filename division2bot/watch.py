"""Watch matching for the Escalation post. No Discord and no network."""

from __future__ import annotations

from dataclasses import dataclass

from division2bot.catalog import Catalog, normalize
from division2bot.snapshot import Snapshot

WATCH_LIMIT = 25
KINDS = ("brand", "gear_set", "slot", "weapon")

SLOTS = {
    "mask": "Masks",
    "masks": "Masks",
    "backpack": "Backpacks",
    "backpacks": "Backpacks",
    "chest": "Chests",
    "chests": "Chests",
    "glove": "Gloves",
    "gloves": "Gloves",
    "holster": "Holsters",
    "holsters": "Holsters",
    "knee": "Kneepads",
    "knees": "Kneepads",
    "kneepad": "Kneepads",
    "kneepads": "Kneepads",
}
WEAPONS = {
    "assault rifle": "Assault Rifles",
    "assault rifles": "Assault Rifles",
    "lmg": "LMGs",
    "lmgs": "LMGs",
    "marksman rifle": "Marksman Rifles",
    "marksman rifles": "Marksman Rifles",
    "mmr": "Marksman Rifles",
    "mmrs": "Marksman Rifles",
    "pistol": "Pistols",
    "pistols": "Pistols",
    "rifle": "Rifles",
    "rifles": "Rifles",
    "shotgun": "Shotguns",
    "shotguns": "Shotguns",
    "smg": "SMGs",
    "smgs": "SMGs",
}


@dataclass(frozen=True)
class Watch:
    guild_id: int
    user_id: int
    kind: str
    name: str


def canonical_slot(value: str) -> str | None:
    return SLOTS.get(normalize(value))


def canonical_weapon(value: str) -> str | None:
    return WEAPONS.get(normalize(value))


def resolve_watch_name(kind: str, raw: str, catalog: Catalog) -> str | None:
    """Return the stored name, or None if the watch cannot match real loot."""
    if kind == "slot":
        return canonical_slot(raw)
    if kind == "weapon":
        return canonical_weapon(raw)
    if kind == "brand":
        return _unique_catalog_name(raw, catalog.brands)
    if kind == "gear_set":
        return _unique_catalog_name(raw, catalog.gear_sets)
    return None


def matching_user_ids(
    snapshot: Snapshot, watches: tuple[Watch, ...] | list[Watch]
) -> tuple[int, ...]:
    """Users whose brand, set, slot, or weapon watch hits this snapshot."""
    loot_names = {normalize(item.loot) for item in snapshot.missions}
    weapon = _weapon_key(snapshot.weapon_cache)
    slot = _slot_key(snapshot.gear_cache)
    hits: list[int] = []
    seen: set[int] = set()
    for watch in watches:
        matched = False
        if watch.kind in {"brand", "gear_set"} and normalize(watch.name) in loot_names:
            matched = True
        elif watch.kind == "slot" and _slot_key(watch.name) == slot:
            matched = True
        elif watch.kind == "weapon" and _weapon_key(watch.name) == weapon:
            matched = True
        if matched and watch.user_id not in seen:
            seen.add(watch.user_id)
            hits.append(watch.user_id)
    return tuple(hits)


def mention_content(user_ids: tuple[int, ...] | list[int]) -> str:
    return " ".join(f"<@{user_id}>" for user_id in user_ids)


def delivery_signature(snapshot: Snapshot) -> str:
    missions = "|".join(f"{item.mission}={item.loot}" for item in snapshot.missions)
    return f"{snapshot.date}|{missions}|{snapshot.weapon_cache}|{snapshot.gear_cache}"


def should_deliver(previous_signature: str | None, snapshot: Snapshot) -> bool:
    return previous_signature != delivery_signature(snapshot)


def poll_interval_seconds(hour_utc: int) -> int:
    """10 minutes from 08:00 UTC through 11:59, otherwise hourly."""
    if 8 <= hour_utc < 12:
        return 10 * 60
    return 60 * 60


def _unique_catalog_name(raw: str, items: tuple[object, ...]) -> str | None:
    key = normalize(raw)
    if len(key) < 3:
        return None
    names = [str(item.name) for item in items]
    exact = [name for name in names if normalize(name) == key]
    if len(exact) == 1:
        return exact[0]
    starts = [name for name in names if normalize(name).startswith(key)]
    if len(starts) == 1:
        return starts[0]
    return None


def _slot_key(value: str) -> str:
    return canonical_slot(value) or normalize(value)


def _weapon_key(value: str) -> str:
    return canonical_weapon(value) or normalize(value)
