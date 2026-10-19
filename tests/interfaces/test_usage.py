from sensai.domain.events import BudgetEvent, UsageEvent
from sensai.interfaces.usage import format_metrics, format_usage


def test_shows_short_counts_and_percent():
    assert format_usage(BudgetEvent(used=4100, max_tokens=8192)) == (
        "4.1k / 8.2k tokens (50%)"
    )


def test_keeps_small_counts_exact():
    assert format_usage(BudgetEvent(used=5, max_tokens=800)) == "5 / 800 tokens (0%)"


def test_can_exceed_full():
    assert "(120%)" in format_usage(BudgetEvent(used=1200, max_tokens=1000))


def test_metrics_line_shows_real_counts_rate_and_timings():
    event = UsageEvent(
        prompt_tokens=1024,
        reply_tokens=187,
        prompt_seconds=2.0,
        reply_seconds=16.4,
        load_seconds=0.1,
        total_seconds=18.5,
    )

    assert format_metrics(event) == (
        "prompt 1 024 tok · reply 187 tok · 11.4 tok/s · first token 2.1 s · total 18.5 s"
    )


def test_metrics_line_skips_what_the_provider_did_not_report():
    assert format_metrics(UsageEvent(reply_tokens=5)) == "reply 5 tok"
    assert format_metrics(UsageEvent()) == ""
