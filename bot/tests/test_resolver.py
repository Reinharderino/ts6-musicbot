import pytest
from unittest.mock import patch
from audio.resolver import resolve


FAKE_INFO = {
    "url": "https://example.com/stream.m4a",
    "title": "Never Gonna Give You Up",
    "duration": 213,
    "webpage_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "uploader": "Rick Astley",
}


@pytest.mark.asyncio
async def test_resolve_url_returns_track():
    with patch("audio.resolver._resolve_sync", return_value=FAKE_INFO):
        track = await resolve("https://youtube.com/watch?v=dQw4w9WgXcQ")
    assert track["title"] == "Never Gonna Give You Up"
    assert track["url"] == "https://example.com/stream.m4a"
    assert track["duration"] == 213


@pytest.mark.asyncio
async def test_resolve_search_query_prefixes_ytsearch():
    captured = {}

    def fake_sync(query):
        captured["query"] = query
        return FAKE_INFO

    with patch("audio.resolver._resolve_sync", side_effect=fake_sync):
        await resolve("rick astley")

    assert captured["query"].startswith("ytsearch1:")
    assert "rick astley" in captured["query"]


@pytest.mark.asyncio
async def test_resolve_raises_on_no_result():
    def fail(_):
        raise ValueError("No results found")

    with patch("audio.resolver._resolve_sync", side_effect=fail):
        with pytest.raises(ValueError):
            await resolve("xyzzy not a real song 12345")


@pytest.mark.asyncio
async def test_resolve_handles_playlist_entry():
    info_with_entries = {
        "entries": [FAKE_INFO],
        "webpage_url": "https://youtube.com/playlist?list=xxx",
    }

    def fake_sync(_):
        return info_with_entries

    with patch("audio.resolver._resolve_sync", side_effect=fake_sync):
        track = await resolve("https://youtube.com/playlist?list=xxx")

    assert track["title"] == "Never Gonna Give You Up"
