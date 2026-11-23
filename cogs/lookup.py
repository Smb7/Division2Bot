"""Slash commands for brands, gear sets, named gear, talents, and exotics."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from division2bot.catalog import Catalog
from division2bot.messages import (
    brand_embed,
    exotic_embed,
    gear_embed,
    gear_set_embed,
    talent_embed,
)

_NO_MENTIONS = discord.AllowedMentions.none()


def _choices(names: tuple[str, ...]) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=name[:100], value=name[:100]) for name in names]


class Lookup(commands.Cog):
    def __init__(self, bot: commands.Bot, catalog: Catalog) -> None:
        self.bot = bot
        self.catalog = catalog

    @app_commands.command(name="brand", description="Brand bonuses and the default core")
    @app_commands.describe(name="Brand name")
    async def brand(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ) -> None:
        found = self.catalog.find_brand(name)
        if found is None:
            await interaction.response.send_message("No brand matches that name.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=brand_embed(found), allowed_mentions=_NO_MENTIONS
        )

    @brand.autocomplete("name")
    async def brand_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        return _choices(self.catalog.complete_brands(current))

    @app_commands.command(
        name="gearset", description="Gear set bonuses, including the 4-piece talent"
    )
    @app_commands.describe(name="Gear set name")
    async def gearset(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ) -> None:
        found = self.catalog.find_gear_set(name)
        if found is None:
            await interaction.response.send_message(
                "No gear set matches that name.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=gear_set_embed(found), allowed_mentions=_NO_MENTIONS
        )

    @gearset.autocomplete("name")
    async def gearset_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        return _choices(self.catalog.complete_gear_sets(current))

    @app_commands.command(name="gear", description="Named piece or gear-set piece")
    @app_commands.describe(name="Piece name")
    async def gear(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ) -> None:
        found = self.catalog.find_gear(name)
        if found is None:
            await interaction.response.send_message("No piece matches that name.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=gear_embed(found), allowed_mentions=_NO_MENTIONS
        )

    @gear.autocomplete("name")
    async def gear_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        return _choices(self.catalog.complete_gear(current))

    @app_commands.command(
        name="talent", description="Gear or weapon talent, including a Perfect row"
    )
    @app_commands.describe(name="Talent name")
    async def talent(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ) -> None:
        found = self.catalog.find_talents(name)
        if not found:
            await interaction.response.send_message("No talent matches that name.", ephemeral=True)
            return
        paired = self.catalog.talent_pair(found[0])
        await interaction.response.send_message(
            embed=talent_embed(paired, title=found[0].name),
            allowed_mentions=_NO_MENTIONS,
        )

    @talent.autocomplete("name")
    async def talent_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        return _choices(self.catalog.complete_talents(current))

    @app_commands.command(name="exotic", description="Exotic weapon or gear and its talent")
    @app_commands.describe(name="Exotic name")
    async def exotic(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ) -> None:
        found = self.catalog.find_exotic(name)
        if found is None:
            await interaction.response.send_message("No exotic matches that name.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=exotic_embed(found), allowed_mentions=_NO_MENTIONS
        )

    @exotic.autocomplete("name")
    async def exotic_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        return _choices(self.catalog.complete_exotics(current))
