"""Data shapes for the LLM judge (EV1)."""

from typing import Literal

from pydantic import BaseModel, Field

ClaimVerdict = Literal["supported", "unsupported", "contradicted"]
Score = Field(ge=1, le=5)


class JudgeInput(BaseModel):
    """One reply to grade: what was asked, what was answered, what was retrieved."""

    question: str
    answer: str
    context: str = ""


class Claim(BaseModel):
    """A statement taken from the answer, checked against the retrieved context."""

    text: str
    verdict: ClaimVerdict
    evidence: str = ""


class QualityScores(BaseModel):
    """What the judge model must return for the quality call."""

    relevance: int = Score
    coherence: int = Score
    rationale: str = ""


class ClaimChecks(BaseModel):
    """What the judge model must return for the faithfulness call."""

    claims: list[Claim] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """Outcome for one reply. `error` is set when any judge call failed.

    Scores stay `None` when their call failed, so a broken judge is never
    mistaken for a bad answer. `claims` is empty when there was no context to
    check against: without a source, nothing can be called supported.
    """

    relevance: int | None = None
    coherence: int | None = None
    rationale: str = ""
    claims: list[Claim] = Field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def faithfulness(self) -> float | None:
        """Share of claims the context supports, or None when nothing was checked."""
        if not self.claims:
            return None
        return sum(1 for c in self.claims if c.verdict == "supported") / len(
            self.claims
        )

    @property
    def unverifiable(self) -> list[Claim]:
        """Claims the context does not back up, or contradicts."""
        return [c for c in self.claims if c.verdict != "supported"]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


class JudgeReport(BaseModel):
    verdicts: list[JudgeVerdict]

    @property
    def errors(self) -> int:
        return sum(1 for v in self.verdicts if not v.ok)

    @property
    def mean_relevance(self) -> float | None:
        return _mean([v.relevance for v in self.verdicts if v.relevance is not None])

    @property
    def mean_coherence(self) -> float | None:
        return _mean([v.coherence for v in self.verdicts if v.coherence is not None])

    @property
    def mean_faithfulness(self) -> float | None:
        return _mean(
            [v.faithfulness for v in self.verdicts if v.faithfulness is not None]
        )

    @property
    def unverifiable_count(self) -> int:
        return sum(len(v.unverifiable) for v in self.verdicts)

    def render(self) -> str:
        """Plain-text summary for a terminal."""

        def fmt(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.2f}"

        lines = [
            f"replies judged: {len(self.verdicts)} ({self.errors} with errors)",
            f"relevance (1-5): {fmt(self.mean_relevance)}",
            f"coherence (1-5): {fmt(self.mean_coherence)}",
            f"faithfulness (0-1): {fmt(self.mean_faithfulness)}",
            f"unverifiable statements: {self.unverifiable_count}",
        ]
        for index, verdict in enumerate(self.verdicts, start=1):
            for claim in verdict.unverifiable:
                lines.append(f"#{index} {claim.verdict}: {claim.text}")
            if verdict.error:
                lines.append(f"#{index} error: {verdict.error}")
        return "\n".join(lines)
