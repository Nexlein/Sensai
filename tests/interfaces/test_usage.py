from sensai.domain.events import BudgetEvent
from sensai.interfaces.usage import format_usage


def test_shows_short_counts_and_percent():
    assert format_usage(BudgetEvent(used=4100, max_tokens=8192)) == (
        "4.1k / 8.2k tokens (50%)"
    )


def test_keeps_small_counts_exact():
    assert format_usage(BudgetEvent(used=5, max_tokens=800)) == "5 / 800 tokens (0%)"


def test_can_exceed_full():
    assert "(120%)" in format_usage(BudgetEvent(used=1200, max_tokens=1000))
