from sensai.core.budget.tracker import UsageTracker


def test_add_accumulates_from_prompt_size():
    tracker = UsageTracker(prompt_tokens=100, max_tokens=1000)

    assert tracker.add("abcd").used == 101
    assert tracker.add("abcdefgh").used == 103


def test_empty_chunk_changes_nothing():
    tracker = UsageTracker(prompt_tokens=10, max_tokens=100)

    assert tracker.add("").used == 10


def test_usage_reports_ratio_and_max():
    usage = UsageTracker(prompt_tokens=50, max_tokens=100).add("")

    assert usage.max_tokens == 100
    assert usage.ratio == 0.5


def test_usage_reads_current_state_without_adding():
    tracker = UsageTracker(prompt_tokens=10, max_tokens=100)
    tracker.add("abcd")

    assert tracker.usage.used == 11
    assert tracker.usage.used == 11


def test_can_exceed_the_cap():
    usage = UsageTracker(prompt_tokens=99, max_tokens=100).add("x" * 40)

    assert usage.ratio > 1
