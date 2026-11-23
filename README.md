# Division2Bot

Personal Discord bot for **Tom Clancy's The Division 2**. Slash commands for brands, gear sets, named gear, talents, and exotics, plus Escalation: the weekly mission list, each mission's daily target loot, and the Prototype vendor caches.

Unofficial fan software. Not affiliated with, endorsed by, or connected to Ubisoft or Massive Entertainment. Game names and stats belong to their owners.

## Item and rotation data

Item text is compiled from [div2hub/game-data](https://github.com/div2hub/game-data) (CC-BY-4.0). That license covers the CSV arrangement, not the game. The CSVs are vendored under `data/upstream/` at commit `d70854574ba83b04ce9b508b17b75aca4f3ce017`. `scripts/build_catalog.py` reads those files and writes `data/catalog.json`. The bot loads the JSON only. It does not fetch `main` on startup.

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
python scripts/build_catalog.py
python bot.py
```

`data/catalog.json` is already committed, so the build step is only required after you replace the vendored CSVs.

`.env` is gitignored. Never commit it.

```
DISCORD_TOKEN=
GUILD_ID=
```

The process has to stay running for the morning Escalation post. Running it on this PC is enough for v1.

Run `/escalation channel set` in the channel that should get the morning post, or pass a channel. `/escalation channel clear` turns it off. The bot needs View Channel, Send Messages, and Embed Links there. It does not need Administrator. Your account needs Manage Channels or Administrator to set the channel or override the day.

## Lookups

Slash commands, with autocomplete:

- `/brand` — 1 / 2 / 3-piece bonuses and the default core (weapon damage, armor, or skill tier).
- `/gearset` — 2 / 3 / 4-piece bonuses. The 4-piece talent is resolved to its description. Chest and backpack talents are included when the catalog has them.
- `/gear` — a named piece, a gear-set piece, or a named weapon: slot, brand or gear set, fixed talent, fixed attributes. A generic brand piece is returned only when that is the name you typed. If two pieces share a name, autocomplete includes the slot.
- `/talent` — gear or weapon talent, plus the Perfect row when one exists. Slot or weapon types are shown when compatibility is not `N/A`.
- `/exotic` — exotic weapon or gear, its talent, and its slot or weapon family.
- `/escalation today` — the five missions, each mission's target loot, and both Prototype caches. Credits ProtoTrack when the text feed supplied the snapshot.
- `/escalation set` — admin override when the feed is late or wrong. Requires Manage Channels or Administrator. The bot does not need Administrator. If a channel is set, that override is posted there.
- `/escalation channel set` — post the morning loot in this channel, or pass a channel. `/escalation channel clear` turns the automatic post off.
- `/escalation watch add` — watch a brand, gear set, gear slot, or weapon type. `remove`, `list`, and `clear` manage that list. A match is mentioned on the morning post. The bot does not DM.

Discord cannot run a parent slash command that also has subcommands, so the view is `/escalation today` rather than a bare `/escalation`.

`/ping` reports latency. Leave the channel unset and nothing is posted automatically. `/escalation today` still works.

## Checks

```powershell
pytest
ruff check .
ruff format --check .
pip-audit
```

Pull requests need `lint`, `test`, `audit`, and CodeQL (`analyze`).
