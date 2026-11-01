"""Benchmark timing helpers and tables."""

import pytest

from sensai.eval.bench.timing import Stat, human_seconds, measure, measure_async, table


def test_measure_calls_warmup_then_repeat_times_number():
    calls = []

    stat = measure(lambda: calls.append(1), repeat=3, number=4, warmup=2)

    assert len(calls) == 2 + 3 * 4
    assert len(stat.runs) == 3
    assert stat.best <= stat.median <= stat.worst


def test_measure_async_runs_the_coroutine():
    calls = []

    async def action():
        calls.append(1)

    measure_async(action, repeat=2, warmup=0)

    assert calls == [1, 1]


def test_stat_median():
    assert Stat((3.0, 1.0, 2.0)).median == 2.0


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (2.5, "2.5 s"),
        (0.035, "35.0 ms"),
        (0.00042, "420 µs"),
        (8e-8, "80 ns"),
        (250, "250 s"),
    ],
)
def test_human_seconds_picks_a_readable_unit(seconds, text):
    assert human_seconds(seconds) == text


def test_table_is_a_padded_markdown_table():
    text = table(["a", "long header"], [["value", 1]])

    assert text.splitlines() == [
        "| a     | long header |",
        "| ----- | ----------- |",
        "| value | 1           |",
    ]
