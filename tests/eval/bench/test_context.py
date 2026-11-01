"""Context benchmark: needle in a long prompt, window sizes, silent cut."""

from sensai.eval.bench.context import (
    ANSWER,
    NEEDLE,
    bench_context,
    bench_truncation,
    filler_text,
    haystack,
)

from .fake_ollama import FakeOllama, answer


def test_filler_is_the_french_scenario_corpus():
    assert "bac jaune" in filler_text()


def test_haystack_has_the_size_asked_and_the_needle_at_its_depth():
    text = haystack("ligne\n" * 1000, 3000, 0.5)

    position = text.index(NEEDLE)
    assert 1300 < position < 1700
    assert len(text) == 3000 + len(NEEDLE) + 2


def _reply(payload):
    content = payload["messages"][0]["content"]
    found = NEEDLE in content
    return answer(
        ANSWER if found else "je ne sais pas", prompt_tokens=len(content) // 3
    )


def test_context_runs_each_size_and_depth_with_its_num_ctx():
    fake = FakeOllama(_reply)

    results = bench_context(
        fake.client(), "m", sizes=(2048, 16384), depths=(0.1, 0.9), deep_limit=8192
    )

    assert [(r.num_ctx, r.depth) for r in results] == [
        (2048, 0.1),
        (2048, 0.9),
        (16384, 0.5),
    ]
    assert all(r.found for r in results)
    assert results[0].server_context == 4096


def test_truncation_compares_the_default_window_with_a_big_one():
    fake = FakeOllama(_reply)

    default, sized = bench_truncation(fake.client(), "m", target_tokens=500)

    assert default.num_ctx is None
    assert sized.num_ctx == 8192
    assert "num_ctx" not in fake.chats()[-2]["options"]
