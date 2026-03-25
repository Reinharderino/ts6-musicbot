import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from ts6.chat_listener import ChatListener


def make_client(responses):
    """Returns a mock WebQueryClient that yields responses in sequence."""
    client = MagicMock()
    client.get_text_messages = AsyncMock(side_effect=responses)
    return client


@pytest.mark.asyncio
async def test_calls_callback_on_new_message():
    messages = [
        {"body": [{"msg": "!play test", "invokerid": 5, "invokername": "alice"}]},
        {"body": []},
    ]
    client = make_client(messages + [asyncio.CancelledError()])
    received = []

    async def callback(sender, text):
        received.append((sender, text))

    listener = ChatListener(client, callback, poll_interval=0)
    try:
        await listener.start()
    except asyncio.CancelledError:
        pass

    assert received == [("alice", "!play test")]


@pytest.mark.asyncio
async def test_empty_body_key_handled():
    """API returns {"body": []} when no messages — must not crash."""
    messages = [{"body": []}, asyncio.CancelledError()]
    client = make_client(messages)
    listener = ChatListener(client, AsyncMock(), poll_interval=0)
    try:
        await listener.start()
    except asyncio.CancelledError:
        pass  # clean exit


@pytest.mark.asyncio
async def test_stop_terminates_loop():
    client = make_client([{"body": []}] * 100)
    listener = ChatListener(client, AsyncMock(), poll_interval=0)
    task = asyncio.create_task(listener.start())
    await asyncio.sleep(0)
    await listener.stop()
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_error_in_poll_does_not_crash():
    """Network errors are logged and polling continues."""
    messages = [Exception("network error"), {"body": []}, asyncio.CancelledError()]
    client = make_client(messages)
    listener = ChatListener(client, AsyncMock(), poll_interval=0)
    try:
        await listener.start()
    except asyncio.CancelledError:
        pass
