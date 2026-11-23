"""Escalation slash commands. The scheduler is a later change."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from db import get_snapshot, save_feed_snapshot, save_override
from division2bot.feed import fetch_target_loot
from division2bot.messages import escalation_embed
from division2bot.snapshot import MissionLoot, loot_date, override_snapshot, parse_target_loot

log = logging.getLogger(__name__)
_NO_MENTIONS = discord.AllowedMentions.none()


def can_configure(permissions: discord.Permissions) -> bool:
    return bool(permissions.manage_channels or permissions.administrator)


class Escalation(
    commands.GroupCog, group_name="escalation", group_description="Escalation target loot"
):
    def __init__(self, bot: commands.Bot, database: aiosqlite.Connection) -> None:
        self.bot = bot
        self.database = database
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Division2Bot"})

    async def cog_unload(self) -> None:
        if self.session is not None:
            await self.session.close()

    @app_commands.command(
        name="today", description="Today's Escalation missions and Prototype caches"
    )
    @app_commands.guild_only()
    async def today(self, interaction: discord.Interaction) -> None:
        day = loot_date(datetime.now(UTC))
        stored = await get_snapshot(self.database, day)
        if stored is not None and stored[1] == "override":
            await interaction.response.send_message(
                embed=escalation_embed(stored[0], origin="override"),
                allowed_mentions=_NO_MENTIONS,
            )
            return
        await interaction.response.defer()
        if self.session is None:
            await interaction.followup.send("The feed client is not ready.", ephemeral=True)
            return
        text = await fetch_target_loot(self.session)
        snapshot = parse_target_loot(text) if text else None
        if snapshot is None:
            log.warning("Escalation feed unavailable or not the expected text shape")
            await interaction.followup.send(
                "The ProtoTrack feed is unavailable or not the expected shape. "
                "Nothing was invented. An admin can set the day with /escalation set.",
                ephemeral=True,
            )
            return
        await save_feed_snapshot(self.database, snapshot)
        current = await get_snapshot(self.database, snapshot.date)
        shown, origin = current if current is not None else (snapshot, "feed")
        note = None
        if snapshot.date != day and origin == "feed":
            note = (
                f"The feed date is {snapshot.date}. The current loot date is {day}. "
                "This is the published text, not a guessed day."
            )
        await interaction.followup.send(
            embed=escalation_embed(shown, origin=origin, note=note),
            allowed_mentions=_NO_MENTIONS,
        )

    @app_commands.command(
        name="set", description="Override the loot snapshot when the feed is late or wrong"
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    @app_commands.describe(
        date="Loot date, YYYY-MM-DD",
        mission_1="First mission",
        loot_1="First mission target loot",
        mission_2="Second mission",
        loot_2="Second mission target loot",
        mission_3="Third mission",
        loot_3="Third mission target loot",
        mission_4="Fourth mission",
        loot_4="Fourth mission target loot",
        mission_5="Fifth mission",
        loot_5="Fifth mission target loot",
        weapon_cache="Prototype weapon cache",
        gear_cache="Prototype gear cache",
    )
    async def set_day(
        self,
        interaction: discord.Interaction,
        date: app_commands.Range[str, 10, 10],
        mission_1: app_commands.Range[str, 1, 100],
        loot_1: app_commands.Range[str, 1, 100],
        mission_2: app_commands.Range[str, 1, 100],
        loot_2: app_commands.Range[str, 1, 100],
        mission_3: app_commands.Range[str, 1, 100],
        loot_3: app_commands.Range[str, 1, 100],
        mission_4: app_commands.Range[str, 1, 100],
        loot_4: app_commands.Range[str, 1, 100],
        mission_5: app_commands.Range[str, 1, 100],
        loot_5: app_commands.Range[str, 1, 100],
        weapon_cache: app_commands.Range[str, 1, 100],
        gear_cache: app_commands.Range[str, 1, 100],
    ) -> None:
        if not can_configure(interaction.permissions):
            await interaction.response.send_message(
                "Manage Channels or Administrator is required.",
                ephemeral=True,
            )
            return
        snapshot = override_snapshot(
            date=date,
            missions=(
                MissionLoot(mission_1, loot_1),
                MissionLoot(mission_2, loot_2),
                MissionLoot(mission_3, loot_3),
                MissionLoot(mission_4, loot_4),
                MissionLoot(mission_5, loot_5),
            ),
            weapon_cache=weapon_cache,
            gear_cache=gear_cache,
            updated="admin",
        )
        if snapshot is None:
            await interaction.response.send_message(
                "That override is not a valid snapshot. Nothing was saved.",
                ephemeral=True,
            )
            return
        await save_override(self.database, snapshot)
        await interaction.response.send_message(
            "Saved the admin override. The feed will not replace this date.",
            embed=escalation_embed(snapshot, origin="override"),
            allowed_mentions=_NO_MENTIONS,
        )
