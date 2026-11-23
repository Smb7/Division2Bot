# Division2Bot

Personal Discord bot for **Tom Clancy's The Division 2**. Slash commands for brands, gear sets, named gear, talents, and exotics, plus Escalation: the weekly mission list, each mission's daily target loot, and the Prototype vendor caches.

This repository is the scaffold. `/ping` is the only command until the lookup and Escalation pull requests land. The bot is unofficial fan software. It is not affiliated with, endorsed by, or connected to Ubisoft or Massive Entertainment. Game names and stats belong to their owners.

## Item and rotation data

Item text is compiled from [div2hub/game-data](https://github.com/div2hub/game-data) (CC-BY-4.0). That license covers the CSV arrangement, not the game. The catalog is pinned to a commit and built offline; the bot does not fetch `main` on startup. A commit pin is recorded when the catalog is vendored.

Escalation rotations come from the public ProtoTrack text feed when that feature lands. Posts credit ProtoTrack. This bot does not copy ProtoTrack's images or branding.

Resets, once Escalation is wired up:

- Daily targeted loot and Prototype caches: **08:00 UTC**
- Weekly mission list: **Tuesday 08:00 UTC**

## Discord application

Create the application yourself. Do not put the token in git, chat, or Actions logs.

1. Open [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2. Bot → Reset Token. Put the token in a local `.env` only.
3. Leave privileged intents off. Slash commands do not need Message Content, Server Members, or Presence.
4. OAuth2 URL Generator: scopes `bot` and `applications.commands`. Bot permissions: View Channels, Send Messages, Embed Links. Do not request Administrator.
5. Invite the bot to your server.
6. Enable Discord Developer Mode, right-click the server, Copy Server ID, and set `GUILD_ID` in `.env`.

While `GUILD_ID` is set, the bot syncs slash commands to that guild from `setup_hook` on startup so they show up immediately. It does not sync on every reconnect, and it does not sync globally on startup.

## Run it

```powershell
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python bot.py
```

`.env` is gitignored. Never commit it.

```
DISCORD_TOKEN=
GUILD_ID=
```

The process has to stay running for the morning Escalation post. Running it on this PC is enough for v1.

Leave `/escalation channel` unset and the bot will not post automatically. People can still run `/escalation` once that command exists. Point it at a channel with `/escalation channel set` in that channel (Manage Channels or Administrator on your account; the bot itself does not need Administrator).

## Checks

```powershell
pytest
ruff check .
ruff format --check .
pip-audit
```

Pull requests need `lint`, `test`, `audit`, and CodeQL (`analyze`).
