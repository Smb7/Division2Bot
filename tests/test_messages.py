from pathlib import Path

from division2bot.catalog import load_catalog
from division2bot.messages import (
    FIELD_LIMIT,
    brand_embed,
    escalation_embed,
    exotic_embed,
    gear_embed,
    gear_set_embed,
    talent_embed,
)
from division2bot.snapshot import parse_target_loot


def test_brand_embed_uses_humanized_bonuses() -> None:
    catalog = load_catalog()
    grupo = catalog.find_brand("Grupo Sombra S.A.")
    assert grupo is not None
    embed = brand_embed(grupo)
    assert embed.title == "Grupo Sombra S.A."
    values = [field.value for field in embed.fields]
    assert "Weapon Damage" in values
    assert any("Critical Hit Damage 13%" in value for value in values)
    assert all("stat:" not in value for value in values)
    assert embed.footer is not None
    assert "div2hub/game-data" in embed.footer.text
    assert "Ubisoft" in embed.footer.text


def test_gear_set_embed_resolves_four_piece_and_chest() -> None:
    catalog = load_catalog()
    strikers = catalog.find_gear_set("Striker's Battlegear")
    assert strikers is not None
    embed = gear_set_embed(strikers)
    names = [field.name for field in embed.fields]
    values = "\n".join(field.value for field in embed.fields)
    assert "4-piece" in names
    assert "Striker's Gamble" in values
    assert "talent:" not in values
    assert any(name.startswith("Chest: Press the Advantage") for name in names)
    assert any(name.startswith("Backpack: Risk Management") for name in names)


def test_gear_and_talent_and_exotic_embeds() -> None:
    catalog = load_catalog()
    gloves = catalog.find_gear("Contractor's Gloves")
    assert gloves is not None
    gear = gear_embed(gloves)
    assert gear.title == "Contractor's Gloves"
    assert any(field.value == "Gloves" for field in gear.fields)
    assert any("Damage to Armor 8%" in field.value for field in gear.fields)
    assert all("fixed:" not in field.value for field in gear.fields)

    obliterate = catalog.find_talents("Obliterate")[0]
    talent = talent_embed(catalog.talent_pair(obliterate), title=obliterate.name)
    assert talent.title == "Obliterate"
    joined = "\n".join(f"{field.name}\n{field.value}" for field in talent.fields)
    assert "Chest" in joined
    assert "Perfect Obliterate" in joined
    assert "24" in joined

    elmo = catalog.find_exotic("St. Elmo's Engine")
    assert elmo is not None
    exotic = exotic_embed(elmo)
    assert exotic.title == "St. Elmo's Engine"
    assert any(field.name == "Actum Est" for field in exotic.fields)
    assert exotic.footer is not None
    assert "One exotic weapon and one exotic gear piece" in exotic.footer.text
    assert all(len(field.value) <= FIELD_LIMIT for field in exotic.fields)


def test_escalation_embed_credits_the_feed_and_labels_an_override() -> None:
    text = (Path(__file__).resolve().parent / "fixtures" / "target-loot-current.txt").read_text(
        encoding="utf-8"
    )
    snapshot = parse_target_loot(text)
    assert snapshot is not None
    feed = escalation_embed(snapshot, origin="feed")
    assert feed.title == "Escalation target loot 2026-11-22"
    assert (
        len(
            [
                field
                for field in feed.fields
                if field.name not in {"Prototype weapon cache", "Prototype gear cache"}
            ]
        )
        == 5
    )
    assert any(field.value == "Assault Rifles" for field in feed.fields)
    assert any(field.value == "Masks" for field in feed.fields)
    assert "ProtoTrack" in (feed.footer.text or "")
    assert "08:00 UTC" in (feed.description or "") or "08:00 UTC" in (
        feed.description or ""
    ).replace("08:00", "08:00")
    assert "Next reset: 2026-11-23 08:00 UTC" in (feed.description or "")

    override = escalation_embed(snapshot, origin="override")
    assert override.description is not None
    assert "Admin override" in override.description
    assert "ProtoTrack" not in (override.footer.text or "")
