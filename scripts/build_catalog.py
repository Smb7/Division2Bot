"""Build data/catalog.json from the vendored div2hub CSVs.

Reads local files only. A Title Update refresh is a chore pull request that
replaces data/upstream and re-runs this script. The bot never fetches main.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "data" / "upstream"
OUTPUT = ROOT / "data" / "catalog.json"
SOURCE_REPO = "https://github.com/div2hub/game-data"
SOURCE_LICENSE = "CC-BY-4.0"

GEAR_SLOTS = {
    "gear/masks.csv": "Mask",
    "gear/backpacks.csv": "Backpack",
    "gear/chests.csv": "Chest",
    "gear/gloves.csv": "Gloves",
    "gear/holsters.csv": "Holster",
    "gear/knees.csv": "Kneepads",
}
WEAPON_FAMILIES = {
    "weapons/assault_rifles.csv": "Assault Rifle",
    "weapons/lmgs.csv": "LMG",
    "weapons/mmrs.csv": "Marksman Rifle",
    "weapons/pistols.csv": "Pistol",
    "weapons/rifles.csv": "Rifle",
    "weapons/shotguns.csv": "Shotgun",
    "weapons/smgs.csv": "SMG",
}
GEAR_VALUE_COLUMNS = ("core_1", "core_2", "core_3", "minor_1", "minor_2", "minor_3", "talent_slot")
WEAPON_VALUE_COLUMNS = (
    "core_1",
    "core_2",
    "core_3",
    "minor_1",
    "minor_2",
    "minor_3",
    "talent_slot",
)


def build_catalog(upstream: Path) -> dict[str, object]:
    """Parse pinned CSVs into the JSON object the bot loads."""
    commit = _commit(upstream)
    stats = _stats(upstream)
    attributes = _attributes(upstream)
    talent_names = _talent_names(upstream)
    attribute_ids = set(attributes)
    return {
        "source": {
            "repo": SOURCE_REPO,
            "commit": commit,
            "license": SOURCE_LICENSE,
        },
        "stats": stats,
        "attributes": attributes,
        "brands": _brands(upstream),
        "gear_sets": _gear_sets(upstream),
        "talents": _talents(upstream),
        "gear": _pieces(upstream, GEAR_SLOTS, talent_names, attribute_ids),
        "weapons": _weapons(upstream, talent_names, attribute_ids),
    }


def _commit(upstream: Path) -> str:
    text = _read(upstream, "COMMIT").strip()
    if len(text) != 40 or any(char not in "0123456789abcdef" for char in text):
        raise SystemExit("data/upstream/COMMIT must be a 40-character git sha")
    return text


def _read(upstream: Path, relative: str) -> str:
    path = (upstream / relative).resolve()
    root = upstream.resolve()
    if not path.is_relative_to(root):
        raise SystemExit(f"Refusing path outside upstream: {relative}")
    if not path.is_file():
        raise SystemExit(f"Missing vendored file: {relative}")
    return path.read_text(encoding="utf-8-sig")


def _rows(upstream: Path, relative: str) -> list[dict[str, str]]:
    text = _read(upstream, relative)
    return list(csv.DictReader(text.splitlines()))


def _cell(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _flag(value: str) -> bool | None:
    folded = value.strip().upper()
    if folded == "TRUE":
        return True
    if folded == "FALSE":
        return False
    return None


def _stats(upstream: Path) -> dict[str, str]:
    stats: dict[str, str] = {}
    for row in _rows(upstream, "stats.csv"):
        stat_id = _cell(row, "id")
        name = _cell(row, "name")
        if not stat_id or not name:
            continue
        stats[stat_id] = name
    return stats


def _attributes(upstream: Path) -> dict[str, dict[str, str]]:
    attributes: dict[str, dict[str, str]] = {}
    for row in _rows(upstream, "attributes.csv"):
        attr_id = _cell(row, "id")
        stat_id = _cell(row, "stat_id")
        if not attr_id or not stat_id:
            continue
        attributes[attr_id] = {
            "stat_id": stat_id,
            "min": _cell(row, "range_min"),
            "max": _cell(row, "range_max"),
        }
    return attributes


def _talent_names(upstream: Path) -> set[str]:
    names: set[str] = set()
    for relative in ("gear/gear_talents.csv", "weapons/weapon_talents.csv"):
        for row in _rows(upstream, relative):
            name = _cell(row, "name")
            description = _cell(row, "description")
            if name and description:
                names.add(name)
    return names


def _brands(upstream: Path) -> list[dict[str, object]]:
    brands: list[dict[str, object]] = []
    for row in _rows(upstream, "gear/brand_sets.csv"):
        name = _cell(row, "name")
        core = _cell(row, "default_core_stat_id")
        bonuses = {
            "1": _cell(row, "1pc_bonus"),
            "2": _cell(row, "2pc_bonus"),
            "3": _cell(row, "3pc_bonus"),
        }
        if not name or not core or not any(bonuses.values()):
            continue
        brands.append({"name": name, "core": core, "bonuses": bonuses})
    return brands


def _gear_sets(upstream: Path) -> list[dict[str, object]]:
    gear_sets: list[dict[str, object]] = []
    for row in _rows(upstream, "gear/gear_sets.csv"):
        name = _cell(row, "name")
        core = _cell(row, "default_core_stat_id")
        bonuses = {
            "1": _cell(row, "1pc_bonus"),
            "2": _cell(row, "2pc_bonus"),
            "3": _cell(row, "3pc_bonus"),
            "4": _cell(row, "4pc_bonus"),
        }
        if not name or not core or not any(bonuses[key] for key in ("2", "3", "4")):
            continue
        gear_sets.append({"name": name, "core": core, "bonuses": bonuses})
    return gear_sets


def _talents(upstream: Path) -> list[dict[str, str]]:
    talents: list[dict[str, str]] = []
    sources = (
        ("gear/gear_talents.csv", "gear"),
        ("weapons/weapon_talents.csv", "weapon"),
    )
    for relative, kind in sources:
        for row in _rows(upstream, relative):
            name = _cell(row, "name")
            description = _cell(row, "description")
            compatibility = _cell(row, "compatibility")
            if not name or not description or not compatibility:
                continue
            talents.append(
                {
                    "name": name,
                    "kind": kind,
                    "compatibility": compatibility,
                    "description": description,
                }
            )
    return talents


def _pieces(
    upstream: Path,
    slots: dict[str, str],
    talent_names: set[str],
    attribute_ids: set[str],
) -> list[dict[str, object]]:
    pieces: list[dict[str, object]] = []
    for relative, slot in slots.items():
        for row in _rows(upstream, relative):
            parsed = _item_row(row, talent_names, attribute_ids, GEAR_VALUE_COLUMNS)
            if parsed is None:
                continue
            name, named, exotic, talent, attributes = parsed
            pieces.append(
                {
                    "name": name,
                    "slot": slot,
                    "brand": _blank_as_none(_cell(row, "brand_set")),
                    "gear_set": _blank_as_none(_cell(row, "gear_set")),
                    "named": named,
                    "exotic": exotic,
                    "talent": talent,
                    "attributes": attributes,
                }
            )
    return pieces


def _weapons(
    upstream: Path,
    talent_names: set[str],
    attribute_ids: set[str],
) -> list[dict[str, object]]:
    weapons: list[dict[str, object]] = []
    for relative, family in WEAPON_FAMILIES.items():
        for row in _rows(upstream, relative):
            parsed = _item_row(row, talent_names, attribute_ids, WEAPON_VALUE_COLUMNS)
            if parsed is None:
                continue
            name, named, exotic, talent, attributes = parsed
            weapons.append(
                {
                    "name": name,
                    "family": family,
                    "named": named,
                    "exotic": exotic,
                    "talent": talent,
                    "attributes": attributes,
                }
            )
    return weapons


def _item_row(
    row: dict[str, str],
    talent_names: set[str],
    attribute_ids: set[str],
    columns: tuple[str, ...],
) -> tuple[str, bool, bool, str | None, list[str]] | None:
    name = _cell(row, "name")
    named = _flag(_cell(row, "is_named"))
    exotic = _flag(_cell(row, "is_exotic"))
    if not name or named is None or exotic is None:
        return None
    talent: str | None = None
    attributes: list[str] = []
    for column in columns:
        token = _fixed_token(_cell(row, column))
        if token is None:
            continue
        if token in talent_names and talent is None:
            talent = token
            continue
        if token in attribute_ids:
            attributes.append(token)
    return name, named, exotic, talent, attributes


def _fixed_token(value: str) -> str | None:
    if not value.startswith("fixed:"):
        return None
    token = value.removeprefix("fixed:").strip()
    return token or None


def _blank_as_none(value: str) -> str | None:
    if not value or value == "N/A":
        return None
    return value


def main() -> None:
    payload = build_catalog(UPSTREAM)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    brands = payload["brands"]
    gear_sets = payload["gear_sets"]
    talents = payload["talents"]
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({len(brands)} brands, {len(gear_sets)} gear sets, {len(talents)} talents)"
    )


if __name__ == "__main__":
    sys.exit(main())
