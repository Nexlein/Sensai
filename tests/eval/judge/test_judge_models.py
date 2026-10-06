import pytest
from pydantic import ValidationError

from sensai.eval.judge import Claim, JudgeReport, JudgeVerdict
from sensai.eval.judge.models import QualityScores


def _claim(verdict: str) -> Claim:
    return Claim(text=f"a {verdict} claim", verdict=verdict)


def test_faithfulness_is_the_supported_share():
    verdict = JudgeVerdict(claims=[_claim("supported"), _claim("unsupported")])
    assert verdict.faithfulness == 0.5


def test_faithfulness_is_none_without_claims():
    assert JudgeVerdict().faithfulness is None
    assert JudgeVerdict().unverifiable == []


def test_unknown_claim_verdict_is_rejected():
    with pytest.raises(ValidationError):
        Claim(text="x", verdict="maybe")


@pytest.mark.parametrize("value", [0, 6, -1])
def test_scores_outside_one_to_five_are_rejected(value):
    with pytest.raises(ValidationError):
        QualityScores(relevance=value, coherence=3)


def test_error_verdict_is_not_ok_and_has_no_scores():
    verdict = JudgeVerdict(error="boom")
    assert not verdict.ok
    assert verdict.relevance is None


def test_empty_report_has_no_means():
    report = JudgeReport(verdicts=[])
    assert report.mean_relevance is None
    assert report.mean_coherence is None
    assert report.mean_faithfulness is None
    assert "replies judged: 0" in report.render()


def test_report_means_skip_verdicts_that_failed():
    report = JudgeReport(
        verdicts=[
            JudgeVerdict(relevance=5, coherence=3, claims=[_claim("supported")]),
            JudgeVerdict(relevance=3, coherence=5, claims=[_claim("unsupported")]),
            JudgeVerdict(error="boom"),
        ]
    )
    assert report.mean_relevance == 4
    assert report.mean_coherence == 4
    assert report.mean_faithfulness == 0.5
    assert report.errors == 1
    assert report.unverifiable_count == 1


def test_render_lists_unverifiable_statements_and_errors():
    report = JudgeReport(
        verdicts=[
            JudgeVerdict(relevance=4, coherence=4, claims=[_claim("contradicted")]),
            JudgeVerdict(error="quality: judge timed out after 60s"),
        ]
    )
    rendered = report.render()
    assert "#1 contradicted: a contradicted claim" in rendered
    assert "#2 error: quality: judge timed out after 60s" in rendered
    assert "n/a" not in rendered.splitlines()[1]
