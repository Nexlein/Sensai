import asyncio
from collections.abc import AsyncIterator

import pytest

from sensai.domain.events import Event, TextChunkEvent
from sensai.interfaces import thinking
from sensai.interfaces.thinking import Thinking, format_thinking


@pytest.fixture(autouse=True)
def fast_clock(monkeypatch):
    monkeypatch.setattr(thinking, "GRACE_SECONDS", 0.05)
    monkeypatch.setattr(thinking, "TICK_SECONDS", 0.05)


def recorder():
    calls: list[int | None] = []

    async def show(elapsed: int | None) -> None:
        calls.append(elapsed)

    return calls, Thinking(show)


def chunk(text: str) -> TextChunkEvent:
    return TextChunkEvent(content=text)


async def after(delay: float, *items: Event) -> AsyncIterator[Event]:
    await asyncio.sleep(delay)
    for item in items:
        yield item


def test_format_thinking_shows_seconds_and_how_to_stop():
    assert format_thinking(14, "Esc") == "thinking… 14s · Esc to stop"


async def test_events_pass_through_unchanged_and_in_order():
    calls, watcher = recorder()

    seen = [e async for e in watcher.watch(after(0, chunk("a"), chunk("b")))]

    assert [e.content for e in seen] == ["a", "b"]
    assert calls == []


async def test_a_fast_reply_never_shows_the_indicator():
    calls, watcher = recorder()

    _ = [e async for e in watcher.watch(after(0.01, chunk("a")))]

    assert calls == []


async def test_a_slow_reply_ticks_then_clears_before_the_event_arrives():
    calls, watcher = recorder()
    order: list[str] = []

    async for _ in watcher.watch(after(0.4, chunk("a"))):
        order.append("event")
        order.append(f"last-call={calls[-1]}")

    assert calls[0] == 0
    assert len(calls) >= 3
    assert calls[-1] is None
    assert order == ["event", "last-call=None"]


async def test_hold_clears_the_indicator_and_pauses_it():
    calls, watcher = recorder()
    release = asyncio.Event()

    async def events() -> AsyncIterator[Event]:
        async with watcher.hold():
            await release.wait()
        yield chunk("a")

    async def release_later() -> None:
        await asyncio.sleep(0.3)
        release.set()

    task = asyncio.ensure_future(release_later())
    _ = [e async for e in watcher.watch(events())]
    await task

    # Nothing was shown while held: the wait was for the user, not the model.
    assert [c for c in calls if c is not None] == []


async def test_time_spent_held_does_not_count_as_thinking_time():
    calls, watcher = recorder()

    async def events() -> AsyncIterator[Event]:
        async with watcher.hold():
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.2)
        yield chunk("a")

    _ = [e async for e in watcher.watch(events())]

    shown = [c for c in calls if c is not None]
    assert shown  # it resumed after the hold
    assert max(shown) == 0  # elapsed restarted at the hold's end (all under 1 s)


async def test_cancellation_clears_the_indicator():
    calls, watcher = recorder()

    async def consume() -> None:
        async for _ in watcher.watch(after(5, chunk("a"))):
            pass

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls[0] == 0
    assert calls[-1] is None


async def test_errors_from_the_stream_propagate_and_clear():
    calls, watcher = recorder()

    async def failing() -> AsyncIterator[Event]:
        await asyncio.sleep(0.2)
        raise ValueError("boom")
        yield  # pragma: no cover

    with pytest.raises(ValueError, match="boom"):
        async for _ in watcher.watch(failing()):
            pass

    assert calls[-1] is None
