"""Timing helpers and plain-text tables shared by every benchmark."""

import asyncio
import statistics
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Stat:
    """Wall-clock times of repeated runs, in seconds."""

    runs: tuple[float, ...]

    @property
    def median(self) -> float:
        return statistics.median(self.runs)

    @property
    def best(self) -> float:
        return min(self.runs)

    @property
    def worst(self) -> float:
        return max(self.runs)


def measure(
    action: Callable[[], Any], repeat: int = 5, number: int = 1, warmup: int = 1
) -> Stat:
    """Time `action`: `repeat` samples, each the mean of `number` calls."""
    for _ in range(warmup):
        action()
    runs = []
    for _ in range(repeat):
        start = time.perf_counter()
        for _ in range(number):
            action()
        runs.append((time.perf_counter() - start) / number)
    return Stat(tuple(runs))


def measure_async(
    action: Callable[[], Awaitable[Any]],
    repeat: int = 5,
    number: int = 1,
    warmup: int = 1,
) -> Stat:
    """`measure` for a coroutine function, on one event loop."""
    loop = asyncio.new_event_loop()
    try:
        return measure(
            lambda: loop.run_until_complete(action()), repeat, number, warmup
        )
    finally:
        loop.close()


def human_seconds(seconds: float) -> str:
    """`1.2 s`, `35 ms`, `420 µs`, `80 ns`."""
    for unit, scale in (("s", 1.0), ("ms", 1e-3), ("µs", 1e-6)):
        if seconds >= scale:
            value = seconds / scale
            return f"{value:.1f} {unit}" if value < 100 else f"{value:.0f} {unit}"
    return f"{seconds * 1e9:.0f} ns"


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """A Markdown table, padded so it also reads well in a terminal."""
    cells = [[str(cell) for cell in row] for row in rows]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in cells))
        if cells
        else len(headers[i])
        for i in range(len(headers))
    ]

    def line(values: Sequence[str]) -> str:
        return "| " + " | ".join(v.ljust(w) for v, w in zip(values, widths)) + " |"

    return "\n".join(
        [line(headers), line(["-" * w for w in widths]), *(line(row) for row in cells)]
    )
