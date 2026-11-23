"""Escalation slash commands and the morning post."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

from db import (
    add_watch,
    channel_for_guild,
    clear_watches,
    configured_channels,
    get_snapshot,
    last_delivery_signature,
    list_watches,
    record_delivery,
    remove_watch,
    save_feed_snapshot,
    save_override,
    set_channel,
    watches_for_guild,
)
from division2bot.catalog import Catalog
from division2bot.feed import fetch_target_loot
from division2bot.messages import escalation_embed
from division2bot.snapshot import (
    MissionLoot,
    Snapshot,
    loot_date,
    override_snapshot,
    parse_target_loot,
)
from division2bot.watch import (
    Watch,
    delivery_signature,
    matching_user_ids,
    mention_content,
    poll_interval_seconds,
    resolve_watch_name,
    should_deliver,
)

log = logging.getLogger(__name__)
_NO_MENTIONS = discord.AllowedMentions.none()
_USER_MENTIONS = discord.AllowedMentions(users=True, everyone=False, roles=False)
_KIND_CHOICES = [
    app_commands.Choice(name="Brand", value="brand"),
    app_commands.Choice(name="Gear set", value="gear_set"),
    app_commands.Choice(name="Gear slot", value="slot"),
    app_commands.Choice(name="Weapon type", value="weapon"),
]
_SLOT_NAMES = ("Masks", "Backpacks", "Chests", "Gloves", "Holsters", "Kneepads")
_WEAPON_NAMES = (
    "Assault Rifles",
    "LMGs",
    "Marksman Rifles",
    "Pistols",
    "Rifles",
    "Shotguns",
    "SMGs",
)


def can_configure(permissions: discord.Permissions) -> bool:
    return bool(permissions.manage_channels or permissions.administrator)


class Escalation(
    commands.GroupCog, group_name="escalation", group_description="Escalation target loot"
):
    channel = app_commands.Group(
        name="channel", description="Where the morning Escalation post goes"
    )
    watch = app_commands.Group(name="watch", description="Get pinged when the day's loot matches")

    def __init__(
        self,
        bot: commands.Bot,
        database: aiosqlite.Connection,
        catalog: Catalog,
    ) -> None:
        self.bot = bot
        self.database = database
        self.catalog = catalog
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Division2Bot"})
        self.poll.change_interval(seconds=poll_interval_seconds(datetime.now(UTC).hour))
        self.poll.start()

    async def cog_unload(self) -> None:
        self.poll.cancel()
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
            ephemeral=True,
        )
        if interaction.guild is not None:
            await self._deliver(interaction.guild.id, snapshot, "override")

    @channel.command(name="set", description="Post the morning Escalation loot in this channel")
    @app_commands.describe(channel="Channel to post in. Defaults to the current channel.")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def channel_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not can_configure(interaction.permissions) or interaction.guild is None:
            await interaction.response.send_message(
                "Manage Channels or Administrator is required.",
                ephemeral=True,
            )
            return
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        me = interaction.guild.me
        if me is None or not _bot_can_post(target.permissions_for(me)):
            await interaction.response.send_message(
                "I need View Channel, Send Messages, and Embed Links in that channel.",
                ephemeral=True,
            )
            return
        await set_channel(self.database, interaction.guild.id, target.id)
        await interaction.response.send_message(
            f"Morning Escalation posts will go to {target.mention}.",
            ephemeral=True,
            allowed_mentions=_NO_MENTIONS,
        )

    @channel.command(name="clear", description="Stop the automatic Escalation post")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def channel_clear(self, interaction: discord.Interaction) -> None:
        if not can_configure(interaction.permissions) or interaction.guild is None:
            await interaction.response.send_message(
                "Manage Channels or Administrator is required.",
                ephemeral=True,
            )
            return
        await set_channel(self.database, interaction.guild.id, None)
        await interaction.response.send_message(
            "Automatic Escalation posts are off. /escalation today still works.",
            ephemeral=True,
        )

    @watch.command(name="add", description="Ping when a brand, set, slot, or weapon is in the loot")
    @app_commands.describe(kind="What to watch", name="Brand, gear set, slot, or weapon type")
    @app_commands.choices(kind=_KIND_CHOICES)
    @app_commands.guild_only()
    async def watch_add(
        self,
        interaction: discord.Interaction,
        kind: str,
        name: app_commands.Range[str, 1, 100],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        resolved = resolve_watch_name(kind, name, self.catalog)
        if resolved is None:
            await interaction.response.send_message(
                "No catalog match for that watch. Nothing was saved.",
                ephemeral=True,
            )
            return
        result = await add_watch(
            self.database,
            Watch(interaction.guild.id, interaction.user.id, kind, resolved),
        )
        if result == "limit":
            await interaction.response.send_message("You already have 25 watches.", ephemeral=True)
            return
        if result == "duplicate":
            await interaction.response.send_message(f"Already watching {resolved}.", ephemeral=True)
            return
        await interaction.response.send_message(f"Watching {resolved}.", ephemeral=True)

    @watch_add.autocomplete("name")
    async def watch_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        kind = _choice_so_far(interaction, "kind")
        if kind == "brand":
            names = self.catalog.complete_brands(current)
        elif kind == "gear_set":
            names = self.catalog.complete_gear_sets(current)
        elif kind == "slot":
            names = tuple(name for name in _SLOT_NAMES if current.lower() in name.lower())
        elif kind == "weapon":
            names = tuple(name for name in _WEAPON_NAMES if current.lower() in name.lower())
        else:
            names = self.catalog.complete_brands(current)
        return [app_commands.Choice(name=item[:100], value=item[:100]) for item in names[:25]]

    @watch.command(name="remove", description="Stop watching one loot name")
    @app_commands.describe(kind="What you were watching", name="The watched name")
    @app_commands.choices(kind=_KIND_CHOICES)
    @app_commands.guild_only()
    async def watch_remove(
        self,
        interaction: discord.Interaction,
        kind: str,
        name: app_commands.Range[str, 1, 100],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        resolved = resolve_watch_name(kind, name, self.catalog)
        stored = resolved or name
        removed = await remove_watch(
            self.database,
            Watch(interaction.guild.id, interaction.user.id, kind, stored),
        )
        if not removed:
            await interaction.response.send_message("That watch was not saved.", ephemeral=True)
            return
        await interaction.response.send_message(f"Stopped watching {stored}.", ephemeral=True)

    @watch.command(name="list", description="Show your Escalation watches")
    @app_commands.guild_only()
    async def watch_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        rows = await list_watches(self.database, interaction.guild.id, interaction.user.id)
        if not rows:
            await interaction.response.send_message("You have no watches.", ephemeral=True)
            return
        lines = [f"{row.kind}: {row.name}" for row in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @watch.command(name="clear", description="Remove all of your Escalation watches")
    @app_commands.guild_only()
    async def watch_clear(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        await clear_watches(self.database, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message("Cleared your watches.", ephemeral=True)

    @tasks.loop(minutes=10)
    async def poll(self) -> None:
        try:
            await self._poll_once(datetime.now(UTC))
        except Exception:
            log.exception("Escalation poll failed")
        self.poll.change_interval(seconds=poll_interval_seconds(datetime.now(UTC).hour))

    @poll.before_loop
    async def before_poll(self) -> None:
        await self.bot.wait_until_ready()

    async def _poll_once(self, now: datetime) -> None:
        loaded = await self._snapshot_for_post(now)
        if loaded is None:
            return
        snapshot, origin = loaded
        for guild_id, _channel_id in await configured_channels(self.database):
            previous = await last_delivery_signature(self.database, guild_id)
            if not should_deliver(previous, snapshot):
                continue
            await self._deliver(guild_id, snapshot, origin)

    async def _snapshot_for_post(self, now: datetime) -> tuple[Snapshot, str] | None:
        day = loot_date(now)
        stored = await get_snapshot(self.database, day)
        if stored is not None and stored[1] == "override":
            return stored
        if self.session is None:
            log.warning("Escalation feed client is not ready")
            return None
        text = await fetch_target_loot(self.session)
        snapshot = parse_target_loot(text) if text else None
        if snapshot is None:
            log.warning("Escalation feed unavailable or not the expected text shape")
            return None
        await save_feed_snapshot(self.database, snapshot)
        current = await get_snapshot(self.database, snapshot.date)
        return current

    async def _deliver(self, guild_id: int, snapshot: Snapshot, origin: str) -> None:
        channel_id = await channel_for_guild(self.database, guild_id)
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.DiscordException:
                log.warning("Escalation channel %s could not be fetched", channel_id)
                return
        if not isinstance(channel, discord.TextChannel):
            return
        me = channel.guild.me
        if me is not None and not _bot_can_post(channel.permissions_for(me)):
            log.warning("Missing send permissions in channel %s", channel_id)
            return
        watches = await watches_for_guild(self.database, guild_id)
        user_ids = matching_user_ids(snapshot, watches)
        content = mention_content(user_ids) or None
        await channel.send(
            content=content,
            embed=escalation_embed(snapshot, origin=origin),
            allowed_mentions=_USER_MENTIONS,
        )
        await record_delivery(
            self.database,
            guild_id,
            delivery_signature(snapshot),
            datetime.now(UTC).isoformat(),
        )


def _bot_can_post(permissions: discord.Permissions) -> bool:
    return bool(permissions.view_channel and permissions.send_messages and permissions.embed_links)


def _choice_so_far(interaction: discord.Interaction, name: str) -> str:
    namespace = interaction.namespace
    value = getattr(namespace, name, None)
    if isinstance(value, str):
        return value
    return ""
