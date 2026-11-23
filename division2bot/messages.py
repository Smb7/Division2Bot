"""Discord embeds built from already-humanized catalog records."""

from __future__ import annotations

import discord

from division2bot.catalog import Brand, Exotic, GearHit, GearSet, Talent
from division2bot.snapshot import Snapshot, next_daily_reset

COLOR = discord.Color.from_rgb(184, 92, 36)
FIELD_LIMIT = 1024
TITLE_LIMIT = 256
DATA_FOOTER = "Item data: div2hub/game-data (CC-BY-4.0). Unofficial, not affiliated with Ubisoft."
EXOTIC_FOOTER = f"One exotic weapon and one exotic gear piece. {DATA_FOOTER}"


def brand_embed(brand: Brand) -> discord.Embed:
    embed = discord.Embed(title=_clip(brand.name, TITLE_LIMIT), color=COLOR)
    embed.add_field(name="Core", value=_clip(brand.core), inline=True)
    for bonus in brand.bonuses:
        embed.add_field(name=f"{bonus.pieces}-piece", value=_clip(bonus.text), inline=False)
    embed.set_footer(text=DATA_FOOTER)
    return embed


def gear_set_embed(gear_set: GearSet) -> discord.Embed:
    embed = discord.Embed(title=_clip(gear_set.name, TITLE_LIMIT), color=COLOR)
    embed.add_field(name="Core", value=_clip(gear_set.core), inline=True)
    for bonus in gear_set.bonuses:
        embed.add_field(name=f"{bonus.pieces}-piece", value=_clip(bonus.text), inline=False)
    if gear_set.chest is not None:
        embed.add_field(
            name=f"Chest: {gear_set.chest.name}",
            value=_talent_value(gear_set.chest.description),
            inline=False,
        )
    if gear_set.backpack is not None:
        embed.add_field(
            name=f"Backpack: {gear_set.backpack.name}",
            value=_talent_value(gear_set.backpack.description),
            inline=False,
        )
    embed.set_footer(text=DATA_FOOTER)
    return embed


def gear_embed(piece: GearHit) -> discord.Embed:
    embed = discord.Embed(title=_clip(piece.name, TITLE_LIMIT), color=COLOR)
    embed.add_field(name="Slot", value=_clip(piece.slot), inline=True)
    if piece.brand:
        embed.add_field(name="Brand", value=_clip(piece.brand), inline=True)
    if piece.gear_set:
        embed.add_field(name="Gear set", value=_clip(piece.gear_set), inline=True)
    if piece.talent is not None:
        embed.add_field(
            name=piece.talent.name, value=_talent_value(piece.talent.description), inline=False
        )
    if piece.attributes:
        embed.add_field(name="Fixed", value=_clip("\n".join(piece.attributes)), inline=False)
    embed.set_footer(text=DATA_FOOTER)
    return embed


def talent_embed(talents: tuple[Talent, ...] | list[Talent], *, title: str) -> discord.Embed:
    embed = discord.Embed(title=_clip(title, TITLE_LIMIT), color=COLOR)
    for talent in talents:
        kind = "Gear" if talent.kind == "gear" else "Weapon"
        if talent.compatibility:
            where = ", ".join(talent.compatibility)
            field_name = f"{talent.name} ({kind}, {where})"
        else:
            field_name = f"{talent.name} ({kind})"
        embed.add_field(
            name=_clip(field_name, 256), value=_talent_value(talent.description), inline=False
        )
    embed.set_footer(text=DATA_FOOTER)
    return embed


def exotic_embed(exotic: Exotic) -> discord.Embed:
    embed = discord.Embed(title=_clip(exotic.name, TITLE_LIMIT), color=COLOR)
    embed.add_field(name="Slot", value=_clip(exotic.slot), inline=True)
    if exotic.talent is not None:
        embed.add_field(
            name=exotic.talent.name, value=_talent_value(exotic.talent.description), inline=False
        )
    if exotic.attributes:
        embed.add_field(name="Fixed", value=_clip("\n".join(exotic.attributes)), inline=False)
    embed.set_footer(text=_clip(EXOTIC_FOOTER, 2048))
    return embed


def escalation_embed(snapshot: Snapshot, *, origin: str, note: str | None = None) -> discord.Embed:
    """Render an already-parsed snapshot. ``origin`` is ``feed`` or ``override``."""
    embed = discord.Embed(title=f"Escalation target loot {snapshot.date}", color=COLOR)
    if origin == "override":
        source_line = "Admin override. The feed is not used for this date."
    else:
        source_line = f"Source: {snapshot.source}. Rotation text from ProtoTrack."
    reset = next_daily_reset(snapshot.date).strftime("%Y-%m-%d %H:%M UTC")
    description = f"{source_line}\nNext reset: {reset}"
    if note:
        description = f"{description}\n{note}"
    embed.description = _clip(description, 4096)
    for item in snapshot.missions:
        embed.add_field(name=_clip(item.mission, 256), value=_clip(item.loot), inline=False)
    embed.add_field(name="Prototype weapon cache", value=_clip(snapshot.weapon_cache), inline=True)
    embed.add_field(name="Prototype gear cache", value=_clip(snapshot.gear_cache), inline=True)
    footer = DATA_FOOTER
    if origin == "feed":
        footer = f"Rotation: ProtoTrack public text feed. {DATA_FOOTER}"
    embed.set_footer(text=_clip(footer, 2048))
    return embed


def _talent_value(description: str) -> str:
    text = description.strip()
    if not text:
        return "No description in the catalog."
    return _clip(text)


def _clip(text: str, limit: int = FIELD_LIMIT) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
