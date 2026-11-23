import pytest

import bot


def test_require_token_rejects_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="DISCORD_TOKEN is required"):
        bot.require_token()


def test_require_token_rejects_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "   ")
    with pytest.raises(SystemExit, match="DISCORD_TOKEN is required"):
        bot.require_token()


def test_configured_guild_id_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUILD_ID", raising=False)
    assert bot.configured_guild_id() is None


def test_configured_guild_id_rejects_junk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUILD_ID", "not-a-guild")
    with pytest.raises(SystemExit, match="GUILD_ID"):
        bot.configured_guild_id()
