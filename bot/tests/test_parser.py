import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from commands.parser import CommandParser
import commands.parser as parser_module

TRACK = {"title": "Never Gonna Give You Up", "url": "x", "duration": 213, "uploader": "Rick Astley", "webpage_url": "x"}


@pytest.fixture
def setup():
    parser_module.BOT_NICKNAME = "testbot"
    player = MagicMock()
    player.enqueue = AsyncMock(return_value=1)
    player.skip = AsyncMock()
    player.stop = AsyncMock()
    player.set_volume = AsyncMock()
    player.queue = []
    player.current_track = MagicMock(return_value=None)
    ts = MagicMock()
    ts.send_channel_message = AsyncMock()
    return CommandParser(player, ts), player, ts


@pytest.mark.asyncio
async def test_non_command_ignored(setup):
    parser, player, ts = setup
    await parser.handle("alice", "hello world")
    ts.send_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_message_ignored(setup):
    parser, player, ts = setup
    await parser.handle("testbot", "!play something")
    player.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_play_resolves_and_enqueues(setup):
    parser, player, ts = setup
    with patch("commands.parser.resolve", AsyncMock(return_value=TRACK)):
        await parser.handle("alice", "!play rick astley")
    player.enqueue.assert_awaited_once()
    assert ts.send_channel_message.call_count >= 1


@pytest.mark.asyncio
async def test_play_without_args_sends_error(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!play")
    ts.send_channel_message.assert_awaited_once()
    assert "Uso" in ts.send_channel_message.call_args[0][0]


@pytest.mark.asyncio
async def test_skip_delegates(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!skip")
    player.skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_delegates(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!stop")
    player.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_vol_valid(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!vol 70")
    player.set_volume.assert_awaited_once_with(70)


@pytest.mark.asyncio
async def test_vol_invalid(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!vol abc")
    ts.send_channel_message.assert_awaited_once()
    assert "Uso" in ts.send_channel_message.call_args[0][0]


@pytest.mark.asyncio
async def test_help_sends_message(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!help")
    ts.send_channel_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_queue_empty(setup):
    parser, player, ts = setup
    await parser.handle("alice", "!queue")
    msg = ts.send_channel_message.call_args[0][0]
    assert "vac" in msg.lower() or "empty" in msg.lower()
