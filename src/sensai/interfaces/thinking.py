"""Elapsed-time feedback while the model has not answered yet, shared by both UIs."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sensai.domain.events import Event

# A reply that starts within this many seconds never shows the indicator.
GRACE_SECONDS = 1.0
TICK_SECONDS = 1.0

# Called with the elapsed seconds on every tick, and with None to clear the display.
ShowFn = Callable[[int | None], Awaitable[None]]


def format_thinking(seconds: int, stop_hint: str) -> str:
    return f"thinking… {seconds}s · {stop_hint} to stop"


class Thinking:
    """Report how long the next event takes, so a slow model is not mistaken for a hang."""

    def __init__(self, show: ShowFn) -> None:
        self._show = show
        self._held = 0
        self._shown = False
        self._restart = asyncio.Event()

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        """Pause the indicator while the user is being asked something; the time
        spent waiting for the answer does not count as thinking time."""
        self._held += 1
        await self._clear()
        try:
            yield
        finally:
            self._held -= 1
            self._restart.set()

    async def _clear(self) -> None:
        if self._shown:
            self._shown = False
            await self._show(None)

    async def watch(self, events: AsyncIterator[Event]) -> AsyncIterator[Event]:
        """Yield `events` unchanged, ticking the indicator while one is awaited."""
        loop = asyncio.get_running_loop()
        iterator = events.__aiter__()
        while True:
            pending = asyncio.ensure_future(iterator.__anext__())
            start = loop.time()
            try:
                while True:
                    delay = TICK_SECONDS if self._shown else GRACE_SECONDS
                    self._restart.clear()
                    restart = asyncio.ensure_future(self._restart.wait())
                    try:
                        done, _ = await asyncio.wait(
                            {pending, restart},
                            timeout=delay,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    finally:
                        restart.cancel()
                    if pending in done:
                        break
                    if restart in done:
                        start = loop.time()
                        continue
                    if self._held:
                        continue
                    self._shown = True
                    await self._show(int(loop.time() - start))
            except BaseException:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
                await self._clear()
                raise
            await self._clear()
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield event
