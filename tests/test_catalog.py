import importlib.util
import json
from pathlib import Path

import pytest

from division2bot.catalog import (
    CATALOG_PATH,
    humanize_bonus,
    humanize_slug,
    load_catalog,
    normalize,
)

ROOT = Path(__file__).resolve().parent.parent


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_catalog", ROOT / "scripts" / "build_catalog.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_drops_accents_and_apostrophes() -> None:
    assert normalize("Striker's Battlegear") == "strikers battlegear"
    assert normalize("Česká výroba s.r.o.") == "ceska vyroba s r o"
    assert normalize("Walker, Harris & Co.") == "walker harris co"


def test_humanize_slug_and_bonus_never_emit_raw_stat_tokens() -> None:
    assert humanize_slug("protection-from-elites") == "Protection From Elites"
    stats = {"critical-hit-damage": "Critical Hit Damage", "lmg-damage": "LMG Damage"}
    talents = {"Striker's Gamble": "Hits add a stack."}
    rendered = humanize_bonus(
        "stat:critical-hit-damage:13%|stat:lmg-damage:15%",
        stats,
        talents,
    )
    assert rendered == "Critical Hit Damage 13%\nLMG Damage 15%"
    assert (
        humanize_bonus("talent:Striker's Gamble", stats, talents)
        == "Striker's Gamble: Hits add a stack."
    )
    assert humanize_bonus("N/A", stats, talents) is None
    assert humanize_bonus("", stats, talents) is None
    assert humanize_bonus("not-a-token", stats, talents) is None


def test_catalog_lookups_use_real_item_text() -> None:
    catalog = load_catalog()
    grupo = catalog.find_brand("grupo")
    assert grupo is not None
    assert grupo.name == "Grupo Sombra S.A."
    assert grupo.core == "Weapon Damage"
    assert grupo.bonuses[0].text == "Critical Hit Damage 13%"
    assert "stat:" not in grupo.bonuses[0].text

    ceska = catalog.find_brand("Česká")
    assert ceska is not None
    assert ceska.name == "Ceska Vyroba s.r.o."

    walker = catalog.find_brand("walker harris")
    assert walker is not None
    assert walker.name == "Walker, Harris & Co."

    strikers = catalog.find_gear_set("striker")
    assert strikers is not None
    assert strikers.bonuses[-1].pieces == 4
    assert "Striker's Gamble:" in strikers.bonuses[-1].text
    assert strikers.chest is not None
    assert strikers.chest.name == "Press the Advantage"
    assert "200" in strikers.chest.description
    assert strikers.backpack is not None
    assert strikers.backpack.name == "Risk Management"

    heartbreaker = catalog.find_gear_set("heartbreaker")
    assert heartbreaker is not None
    assert heartbreaker.chest is not None
    assert heartbreaker.chest.name == "Max BPM"

    obliterate = catalog.find_talents("obliterate")
    assert obliterate[0].name == "Obliterate"
    assert obliterate[0].compatibility == ("Chest",)
    paired = catalog.talent_pair(obliterate[0])
    assert [talent.name for talent in paired] == ["Obliterate", "Perfect Obliterate"]

    vigilance = catalog.find_talents("vigilance")
    assert vigilance[0].name == "Vigilance"
    assert "Perfect" not in vigilance[0].name

    gloves = catalog.find_gear("contractors gloves")
    assert gloves is not None
    assert gloves.name == "Contractor's Gloves"
    assert gloves.slot == "Gloves"
    assert gloves.brand == "Petrov Defense Group"
    assert gloves.attributes == ("Damage to Armor 8%",)

    gift = catalog.find_gear("the gift")
    assert gift is not None
    assert gift.talent is not None
    assert gift.talent.name == "Perfect Vigilance"

    generic = catalog.find_gear("5.11 Tactical Mask")
    assert generic is not None
    assert generic.named is False

    assert catalog.find_gear("memento") is None
    assert catalog.find_gear("bulldog") is None
    bulldogs = catalog.match_gear("bulldog")
    assert [piece.slot for piece in bulldogs] == ["Backpack", "Holster"]
    holster = catalog.find_gear("Bulldog (Holster)")
    assert holster is not None
    assert holster.slot == "Holster"
    assert holster.talent is not None
    assert holster.talent.name == "Perfect Composure"
    elmo = catalog.find_exotic("st elmos")
    assert elmo is not None
    assert elmo.name == "St. Elmo's Engine"
    assert elmo.slot == "Assault Rifle"
    assert elmo.talent is not None
    assert elmo.talent.name == "Actum Est"
    assert catalog.find_exotic("regulus") is not None
    assert catalog.find_exotic("memento") is not None


def test_autocomplete_is_capped_and_exact_names_win() -> None:
    catalog = load_catalog()
    assert len(catalog.complete_brands("")) <= 25
    assert len(catalog.complete_brands("a")) <= 25
    assert len(catalog.complete_gear("")) <= 25
    assert len(catalog.complete_talents("perfect")) <= 25
    assert catalog.complete_brands("grupo")[0] == "Grupo Sombra S.A."
    assert set(catalog.complete_gear("bulldog")) == {"Bulldog (Backpack)", "Bulldog (Holster)"}


def test_builder_skips_incomplete_rows_and_keeps_quoted_names(tmp_path: Path) -> None:
    builder = _builder()
    gear = tmp_path / "gear"
    gear.mkdir()
    (gear / "brand_sets.csv").write_text(
        "name,default_core_stat_id,1pc_bonus,2pc_bonus,3pc_bonus\n"
        '"Walker, Harris & Co.",weapon-damage,stat:weapon-damage:6%,'
        "stat:damage-to-armor:5%,stat:health-damage:10%\n"
        ",weapon-damage,stat:armor:1%,stat:armor:1%,stat:armor:1%\n",
        encoding="utf-8",
    )
    brands = builder._brands(tmp_path)
    assert [brand["name"] for brand in brands] == ["Walker, Harris & Co."]

    skipped = builder._item_row(
        {"name": "Mystery", "is_named": "", "is_exotic": "FALSE"},
        set(),
        set(),
        (),
    )
    assert skipped is None
    parsed = builder._item_row(
        {
            "name": "Contractor's Gloves",
            "is_named": "TRUE",
            "is_exotic": "FALSE",
            "talent_slot": "N/A",
            "minor_1": "fixed:damage-to-armor-contractors-gloves",
            "core_1": "type:gear-core",
        },
        {"Perfect Vigilance"},
        {"damage-to-armor-contractors-gloves"},
        ("talent_slot", "minor_1", "core_1"),
    )
    assert parsed is not None
    assert parsed[3] is None
    assert parsed[4] == ["damage-to-armor-contractors-gloves"]


def test_committed_catalog_matches_the_builder() -> None:
    builder = _builder()
    built = builder.build_catalog(ROOT / "data" / "upstream")
    committed = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert built == committed


def test_require_token_still_rejects_a_blank_token(monkeypatch: pytest.MonkeyPatch) -> None:
    import bot

    monkeypatch.setenv("DISCORD_TOKEN", "   ")
    with pytest.raises(SystemExit, match="DISCORD_TOKEN is required"):
        bot.require_token()
