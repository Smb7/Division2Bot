"""Fetch the public ProtoTrack text feed. The body is never executed."""

from __future__ import annotations

import aiohttp

from division2bot.snapshot import FEED_URL, MAX_FEED_CHARS

_TIMEOUT = aiohttp.ClientTimeout(total=10)


async def fetch_target_loot(session: aiohttp.ClientSession) -> str | None:
    """GET the pinned HTTPS feed. Timeouts and non-200 responses return None."""
    try:
        async with session.get(FEED_URL, timeout=_TIMEOUT, allow_redirects=False) as response:
            if response.status != 200:
                return None
            raw = await response.read()
    except (aiohttp.ClientError, TimeoutError):
        return None
    if len(raw) > MAX_FEED_CHARS:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
