"""Division 2 Discord bot entry point."""

from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from cogs.lookup import Lookup
from division2bot.catalog import Catalog, load_catalog

log = logging.getLogger(__name__)


def require_token() -> str:
    """Return the Discord token from the environment.

    Exits if it is missing. The value is never logged.
    """
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN is required")
    return token


def configured_guild_id() -> int | None:
    """Return the development guild id, if ``GUILD_ID`` is set."""
    raw = os.environ.get("GUILD_ID", "").strip()
    if not raw:
        return None
    if not raw.isdecimal():
        raise SystemExit("GUILD_ID must be a numeric server id")
    return int(raw)


class DivisionBot(commands.Bot):
    def __init__(self, catalog: Catalog) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            help_command=None,
        )
        self.catalog = catalog

    async def setup_hook(self) -> None:
        await self.add_cog(Lookup(self, self.catalog))
        self.tree.add_command(ping)
        guild_id = configured_guild_id()
        if guild_id is None:
            log.info("GUILD_ID is unset; skipping command sync")
            return
        guild = discord.Object(id=guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Synced commands to guild %s", guild_id)


@app_commands.command(name="ping", description="Check that the bot is online")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(interaction.client.latency * 1000)
    await interaction.response.send_message(f"Pong ({latency_ms} ms)", ephemeral=True)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token = require_token()
    try:
        catalog = load_catalog()
    except FileNotFoundError as exc:
        raise SystemExit(
            "data/catalog.json is missing. Run: python scripts/build_catalog.py"
        ) from exc
    DivisionBot(catalog).run(token, log_handler=None)


if __name__ == "__main__":
    main()
