"""Load the vendored catalog, humanize bonuses, and search by name."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "catalog.json"
AUTOCOMPLETE_LIMIT = 25

_APOSTROPHES = str.maketrans({"'": "", "’": "", "`": "", "´": ""})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

SLOT_NAMES = {
    "chest": "Chest",
    "backpack": "Backpack",
    "mask": "Mask",
    "gloves": "Gloves",
    "holster": "Holster",
    "kneepads": "Kneepads",
    "assault-rifle": "Assault Rifle",
    "smg": "SMG",
    "lmg": "LMG",
    "rifle": "Rifle",
    "marksman-rifle": "Marksman Rifle",
    "shotgun": "Shotgun",
    "pistol": "Pistol",
}

T = TypeVar("T")


def humanize_slug(slug: str) -> str:
    """Turn ``protection-from-elites`` into ``Protection From Elites``."""
    words = [word for word in slug.replace("_", "-").split("-") if word]
    return " ".join(word.capitalize() for word in words)


def normalize(text: str) -> str:
    """Case-fold, strip accents and apostrophes, and collapse punctuation."""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.translate(_APOSTROPHES).lower()
    return " ".join(_NON_ALNUM.sub(" ", folded).split())


def stat_name(slug: str, stats: dict[str, str]) -> str:
    known = stats.get(slug)
    if known:
        return known
    return humanize_slug(slug)


def humanize_compatibility(raw: str) -> tuple[str, ...]:
    """Return display labels. ``N/A`` and blanks do not apply."""
    text = raw.strip()
    if not text or text == "N/A":
        return ()
    labels: list[str] = []
    for part in text.split("|"):
        part = part.strip()
        if not part or part == "N/A":
            continue
        labels.append(SLOT_NAMES.get(part, humanize_slug(part)))
    return tuple(labels)


def humanize_bonus(raw: str, stats: dict[str, str], talents: dict[str, str]) -> str | None:
    """Render one bonus cell.

    Empty means unknown and is skipped. ``N/A`` means the bonus does not apply.
    ``stat:`` and ``talent:`` tokens are resolved. Anything else is skipped
    rather than shown as a raw ``stat:`` string.
    """
    text = raw.strip()
    if not text or text == "N/A":
        return None
    lines: list[str] = []
    for part in text.split("|"):
        part = part.strip()
        if not part or part == "N/A":
            continue
        if part.startswith("stat:"):
            slug, separator, value = part[5:].rpartition(":")
            if not separator or not slug.strip():
                continue
            lines.append(f"{stat_name(slug.strip(), stats)} {value.strip()}".strip())
        elif part.startswith("talent:"):
            name = part.split(":", 1)[1].strip()
            if not name:
                continue
            description = talents.get(name, "")
            lines.append(f"{name}: {description}" if description else name)
        else:
            continue
    if not lines:
        return None
    return "\n".join(lines)


def format_attribute(
    attr_id: str, attributes: dict[str, dict[str, str]], stats: dict[str, str]
) -> str | None:
    """Format a locked attribute. Unknown ids are not invented into values."""
    attr = attributes.get(attr_id)
    if not attr:
        return None
    name = stat_name(attr.get("stat_id", ""), stats)
    if not name:
        return None
    low = attr.get("min", "").strip()
    high = attr.get("max", "").strip()
    if low and high:
        if low == high:
            return f"{name} {low}"
        return f"{name} {low}–{high}"
    if low:
        return f"{name} {low}"
    return name


@dataclass(frozen=True)
class Bonus:
    pieces: int
    text: str


@dataclass(frozen=True)
class TalentRef:
    name: str
    description: str


@dataclass(frozen=True)
class Brand:
    name: str
    core: str
    bonuses: tuple[Bonus, ...]


@dataclass(frozen=True)
class GearSet:
    name: str
    core: str
    bonuses: tuple[Bonus, ...]
    chest: TalentRef | None
    backpack: TalentRef | None


@dataclass(frozen=True)
class Talent:
    name: str
    kind: str
    compatibility: tuple[str, ...]
    description: str
    perfect_name: str | None = None
    base_name: str | None = None


@dataclass(frozen=True)
class GearHit:
    name: str
    slot: str
    brand: str | None
    gear_set: str | None
    talent: TalentRef | None
    attributes: tuple[str, ...]
    named: bool


@dataclass(frozen=True)
class Exotic:
    name: str
    slot: str
    talent: TalentRef | None
    attributes: tuple[str, ...]


@dataclass(frozen=True)
class _GearRecord:
    name: str
    slot: str
    brand: str | None
    gear_set: str | None
    named: bool
    exotic: bool
    talent: str | None
    attribute_ids: tuple[str, ...]


@dataclass(frozen=True)
class _WeaponRecord:
    name: str
    family: str
    named: bool
    exotic: bool
    talent: str | None
    attribute_ids: tuple[str, ...]


class Catalog:
    def __init__(
        self,
        *,
        source_commit: str,
        brands: tuple[Brand, ...],
        gear_sets: tuple[GearSet, ...],
        talents: tuple[Talent, ...],
        gear: tuple[GearHit, ...],
        named_weapons: tuple[GearHit, ...],
        exotics: tuple[Exotic, ...],
    ) -> None:
        self.source_commit = source_commit
        self.brands = brands
        self.gear_sets = gear_sets
        self.talents = talents
        self.gear = gear
        self.named_weapons = named_weapons
        self.exotics = exotics
        self._talents_by_key = {(talent.kind, normalize(talent.name)): talent for talent in talents}

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> Catalog:
        stats = _string_map(payload.get("stats"))
        attributes = _attribute_map(payload.get("attributes"))
        talent_rows = _dict_list(payload.get("talents"))
        talent_text = {
            str(row.get("name", "")).strip(): str(row.get("description", "")).strip()
            for row in talent_rows
            if str(row.get("name", "")).strip()
        }
        talents = _pair_perfect(_talents_from_rows(talent_rows))
        gear_records = _gear_records(payload.get("gear"))
        weapon_records = _weapon_records(payload.get("weapons"))
        gear_hits = tuple(
            _gear_hit(record, talent_text, attributes, stats) for record in gear_records
        )
        named_weapons = tuple(
            _weapon_hit(record, talent_text, attributes, stats)
            for record in weapon_records
            if record.named and not record.exotic
        )
        exotics = tuple(
            _exotic_from_gear(record, talent_text, attributes, stats)
            for record in gear_records
            if record.exotic
        ) + tuple(
            _exotic_from_weapon(record, talent_text, attributes, stats)
            for record in weapon_records
            if record.exotic
        )
        by_piece = {normalize(hit.name): hit for hit in gear_hits}
        brands = tuple(
            brand
            for row in _dict_list(payload.get("brands"))
            if (brand := _brand_from_row(row, stats, talent_text)) is not None
        )
        gear_sets = tuple(
            gear_set
            for row in _dict_list(payload.get("gear_sets"))
            if (gear_set := _gear_set_from_row(row, stats, talent_text, by_piece)) is not None
        )
        source = payload.get("source")
        commit = ""
        if isinstance(source, dict):
            commit = str(source.get("commit", "")).strip()
        return cls(
            source_commit=commit,
            brands=brands,
            gear_sets=gear_sets,
            talents=talents,
            gear=gear_hits,
            named_weapons=named_weapons,
            exotics=exotics,
        )

    def find_brand(self, query: str) -> Brand | None:
        return _best(query, self.brands, lambda item: item.name)

    def find_gear_set(self, query: str) -> GearSet | None:
        return _best(query, self.gear_sets, lambda item: item.name)

    def find_talents(self, query: str) -> tuple[Talent, ...]:
        """Return the best talent row, plus an exact gear/weapon collision if both match."""
        ranked = _ranked(query, self.talents, lambda item: item.name)
        if not ranked:
            return ()
        best_score = ranked[0][0]
        if best_score[0] == 0:
            return tuple(item for score, item in ranked if score[0] == 0)
        return (ranked[0][1],)

    def talent_pair(self, talent: Talent) -> tuple[Talent, ...]:
        """Base talent first, then the Perfect row when one exists."""
        other_name = talent.perfect_name or talent.base_name
        other = (
            self._talents_by_key.get((talent.kind, normalize(other_name))) if other_name else None
        )
        if other is None:
            return (talent,)
        base, perfect = (other, talent) if talent.base_name else (talent, other)
        return (base, perfect)

    def find_gear(self, query: str) -> GearHit | None:
        """Named pieces, gear-set pieces, named weapons, or an exact generic name.

        A shared name such as Bulldog is not guessed. Use ``Name (Slot)`` or
        :meth:`match_gear` when more than one piece matches.
        """
        matches = self.match_gear(query)
        if len(matches) == 1:
            return matches[0]
        return None

    def match_gear(self, query: str) -> tuple[GearHit, ...]:
        """Return every piece the query identifies.

        One result is a unique hit. More than one means the bare name is shared
        and the slot was not chosen. ``Name (Slot)`` selects one of those pieces.
        """
        query_key = normalize(query)
        if not query_key:
            return ()
        labeled = _labeled_gear((*self._focus_pieces(), *self.named_weapons))
        exact = tuple(piece for label, piece in labeled if normalize(label) == query_key)
        if exact:
            return exact
        bare = tuple(piece for _, piece in labeled if normalize(piece.name) == query_key)
        if bare:
            return bare
        ranked = _ranked(query, labeled, lambda item: item[0])
        if ranked:
            best = ranked[0][0]
            return tuple(piece for score, (_, piece) in ranked if score == best)
        exotic_names = {normalize(item.name) for item in self.exotics}
        return tuple(
            piece
            for piece in self.gear
            if normalize(piece.name) == query_key and query_key not in exotic_names
        )

    def find_exotic(self, query: str) -> Exotic | None:
        return _best(query, self.exotics, lambda item: item.name)

    def complete_brands(self, query: str) -> tuple[str, ...]:
        return _complete(query, [item.name for item in self.brands])

    def complete_gear_sets(self, query: str) -> tuple[str, ...]:
        return _complete(query, [item.name for item in self.gear_sets])

    def complete_talents(self, query: str) -> tuple[str, ...]:
        return _complete(query, [item.name for item in self.talents])

    def complete_gear(self, query: str) -> tuple[str, ...]:
        labels = [label for label, _ in _labeled_gear((*self._focus_pieces(), *self.named_weapons))]
        return _complete(query, labels)

    def complete_exotics(self, query: str) -> tuple[str, ...]:
        return _complete(query, [item.name for item in self.exotics])

    def _focus_pieces(self) -> tuple[GearHit, ...]:
        exotic_names = {normalize(item.name) for item in self.exotics}
        return tuple(
            piece
            for piece in self.gear
            if normalize(piece.name) not in exotic_names
            and (piece.named or piece.gear_set is not None)
        )


def load_catalog(path: Path | None = None) -> Catalog:
    catalog_path = path or CATALOG_PATH
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog.json must be an object")
    return Catalog.from_payload(payload)


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item) for key, item in value.items() if str(key).strip() and str(item).strip()
    }


def _attribute_map(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            continue
        attr_id = str(key).strip()
        stat_id = str(item.get("stat_id", "")).strip()
        if not attr_id or not stat_id:
            continue
        parsed[attr_id] = {
            "stat_id": stat_id,
            "min": str(item.get("min", "")).strip(),
            "max": str(item.get("max", "")).strip(),
        }
    return parsed


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _bonus_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _brand_from_row(
    row: dict[str, object], stats: dict[str, str], talents: dict[str, str]
) -> Brand | None:
    name = str(row.get("name", "")).strip()
    core_id = str(row.get("core", "")).strip()
    if not name or not core_id:
        return None
    bonuses = _bonuses(_bonus_map(row.get("bonuses")), (1, 2, 3), stats, talents)
    if not bonuses:
        return None
    return Brand(name=name, core=stat_name(core_id, stats), bonuses=bonuses)


def _gear_set_from_row(
    row: dict[str, object],
    stats: dict[str, str],
    talents: dict[str, str],
    pieces: dict[str, GearHit],
) -> GearSet | None:
    name = str(row.get("name", "")).strip()
    core_id = str(row.get("core", "")).strip()
    if not name or not core_id:
        return None
    bonuses = _bonuses(_bonus_map(row.get("bonuses")), (2, 3, 4), stats, talents)
    if not bonuses:
        return None
    return GearSet(
        name=name,
        core=stat_name(core_id, stats),
        bonuses=bonuses,
        chest=_piece_talent(pieces, name, "Chest"),
        backpack=_piece_talent(pieces, name, "Backpack"),
    )


def _piece_talent(pieces: dict[str, GearHit], set_name: str, slot: str) -> TalentRef | None:
    hit = pieces.get(normalize(f"{set_name} {slot}"))
    if hit is None or hit.talent is None:
        return None
    return hit.talent


def _bonuses(
    raw: dict[str, str],
    pieces: tuple[int, ...],
    stats: dict[str, str],
    talents: dict[str, str],
) -> tuple[Bonus, ...]:
    built: list[Bonus] = []
    for count in pieces:
        text = humanize_bonus(raw.get(str(count), ""), stats, talents)
        if text:
            built.append(Bonus(pieces=count, text=text))
    return tuple(built)


def _talents_from_rows(rows: list[dict[str, object]]) -> list[Talent]:
    talents: list[Talent] = []
    for row in rows:
        name = str(row.get("name", "")).strip()
        description = str(row.get("description", "")).strip()
        kind = str(row.get("kind", "")).strip()
        if not name or not description or kind not in {"gear", "weapon"}:
            continue
        talents.append(
            Talent(
                name=name,
                kind=kind,
                compatibility=humanize_compatibility(str(row.get("compatibility", ""))),
                description=description,
            )
        )
    return talents


def _pair_perfect(talents: list[Talent]) -> tuple[Talent, ...]:
    by_key = {(talent.kind, normalize(talent.name)): talent for talent in talents}
    paired: list[Talent] = []
    for talent in talents:
        perfect_name = None
        base_name = None
        if talent.name.startswith("Perfect "):
            base = by_key.get((talent.kind, normalize(talent.name.removeprefix("Perfect "))))
            if base is not None:
                base_name = base.name
        else:
            perfect = by_key.get((talent.kind, normalize(f"Perfect {talent.name}")))
            if perfect is not None:
                perfect_name = perfect.name
        paired.append(
            Talent(
                name=talent.name,
                kind=talent.kind,
                compatibility=talent.compatibility,
                description=talent.description,
                perfect_name=perfect_name,
                base_name=base_name,
            )
        )
    return tuple(paired)


def _gear_records(value: object) -> tuple[_GearRecord, ...]:
    records: list[_GearRecord] = []
    for row in _dict_list(value):
        name = str(row.get("name", "")).strip()
        slot = str(row.get("slot", "")).strip()
        if (
            not name
            or not slot
            or not isinstance(row.get("named"), bool)
            or not isinstance(row.get("exotic"), bool)
        ):
            continue
        records.append(
            _GearRecord(
                name=name,
                slot=slot,
                brand=_optional_name(row.get("brand")),
                gear_set=_optional_name(row.get("gear_set")),
                named=bool(row["named"]),
                exotic=bool(row["exotic"]),
                talent=_optional_name(row.get("talent")),
                attribute_ids=_string_tuple(row.get("attributes")),
            )
        )
    return tuple(records)


def _weapon_records(value: object) -> tuple[_WeaponRecord, ...]:
    records: list[_WeaponRecord] = []
    for row in _dict_list(value):
        name = str(row.get("name", "")).strip()
        family = str(row.get("family", "")).strip()
        if (
            not name
            or not family
            or not isinstance(row.get("named"), bool)
            or not isinstance(row.get("exotic"), bool)
        ):
            continue
        records.append(
            _WeaponRecord(
                name=name,
                family=family,
                named=bool(row["named"]),
                exotic=bool(row["exotic"]),
                talent=_optional_name(row.get("talent")),
                attribute_ids=_string_tuple(row.get("attributes")),
            )
        )
    return tuple(records)


def _optional_name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "N/A":
        return None
    return text


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _talent_ref(name: str | None, talents: dict[str, str]) -> TalentRef | None:
    if not name:
        return None
    return TalentRef(name=name, description=talents.get(name, ""))


def _locked_attributes(
    attr_ids: tuple[str, ...],
    attributes: dict[str, dict[str, str]],
    stats: dict[str, str],
) -> tuple[str, ...]:
    locked: list[str] = []
    for attr_id in attr_ids:
        attr = attributes.get(attr_id)
        if not attr:
            continue
        low = attr.get("min", "")
        high = attr.get("max", "")
        if not low or low != high:
            continue
        formatted = format_attribute(attr_id, attributes, stats)
        if formatted:
            locked.append(formatted)
    return tuple(locked)


def _gear_hit(
    record: _GearRecord,
    talents: dict[str, str],
    attributes: dict[str, dict[str, str]],
    stats: dict[str, str],
) -> GearHit:
    return GearHit(
        name=record.name,
        slot=record.slot,
        brand=record.brand,
        gear_set=record.gear_set,
        talent=_talent_ref(record.talent, talents),
        attributes=_locked_attributes(record.attribute_ids, attributes, stats),
        named=record.named,
    )


def _weapon_hit(
    record: _WeaponRecord,
    talents: dict[str, str],
    attributes: dict[str, dict[str, str]],
    stats: dict[str, str],
) -> GearHit:
    return GearHit(
        name=record.name,
        slot=record.family,
        brand=None,
        gear_set=None,
        talent=_talent_ref(record.talent, talents),
        attributes=_locked_attributes(record.attribute_ids, attributes, stats),
        named=record.named,
    )


def _exotic_from_gear(
    record: _GearRecord,
    talents: dict[str, str],
    attributes: dict[str, dict[str, str]],
    stats: dict[str, str],
) -> Exotic:
    return Exotic(
        name=record.name,
        slot=record.slot,
        talent=_talent_ref(record.talent, talents),
        attributes=_locked_attributes(record.attribute_ids, attributes, stats),
    )


def _exotic_from_weapon(
    record: _WeaponRecord,
    talents: dict[str, str],
    attributes: dict[str, dict[str, str]],
    stats: dict[str, str],
) -> Exotic:
    return Exotic(
        name=record.name,
        slot=record.family,
        talent=_talent_ref(record.talent, talents),
        attributes=_locked_attributes(record.attribute_ids, attributes, stats),
    )


def _score(query: str, name: str) -> tuple[int, int, str] | None:
    query_key = normalize(query)
    name_key = normalize(name)
    if not query_key:
        return None
    if name_key == query_key:
        return (0, len(name_key), name_key)
    if name_key.startswith(query_key):
        return (1, len(name_key), name_key)
    if query_key in name_key:
        return (2, len(name_key), name_key)
    return None


def _ranked(
    query: str,
    items: Sequence[T],
    name_of: Callable[[T], str],
) -> list[tuple[tuple[int, int, str], T]]:
    ranked: list[tuple[tuple[int, int, str], T]] = []
    for item in items:
        score = _score(query, name_of(item))
        if score is not None:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0])
    return ranked


def _best(query: str, items: Sequence[T], name_of: Callable[[T], str]) -> T | None:
    ranked = _ranked(query, items, name_of)
    if not ranked:
        return None
    return ranked[0][1]


def _labeled_gear(pieces: Sequence[GearHit]) -> tuple[tuple[str, GearHit], ...]:
    """Suffix the slot when more than one piece shares a normalized name."""
    counts: dict[str, int] = {}
    for piece in pieces:
        key = normalize(piece.name)
        counts[key] = counts.get(key, 0) + 1
    labeled: list[tuple[str, GearHit]] = []
    for piece in pieces:
        if counts[normalize(piece.name)] > 1:
            labeled.append((f"{piece.name} ({piece.slot})", piece))
        else:
            labeled.append((piece.name, piece))
    return tuple(labeled)


def _complete(query: str, names: list[str]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    query_key = normalize(query)
    if not query_key:
        unique.sort(key=normalize)
        return tuple(unique[:AUTOCOMPLETE_LIMIT])
    ranked = [(score, name) for name in unique if (score := _score(query, name)) is not None]
    ranked.sort(key=lambda pair: pair[0])
    return tuple(name for _, name in ranked[:AUTOCOMPLETE_LIMIT])
