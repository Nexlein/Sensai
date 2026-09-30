import pytest

from sensai.eval.adversarial import CASES, CATEGORIES
from sensai.eval.adversarial.corpus import AttackCase


def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))


def test_every_category_has_cases():
    assert {c.category for c in CASES} == set(CATEGORIES)


def test_corpus_covers_both_stages_and_both_languages():
    assert {c.stage for c in CASES} == {"input", "output"}
    assert any("précédentes" in c.payload for c in CASES)


def test_benign_cases_expect_allow():
    benign = [c for c in CASES if c.category == "benign"]
    assert benign
    assert all(c.expect == "allow" for c in benign)


@pytest.mark.parametrize("case", [c for c in CASES if c.secret], ids=lambda c: c.id)
def test_secret_is_really_in_the_payload(case: AttackCase):
    assert case.secret in case.payload


@pytest.mark.parametrize("case", [c for c in CASES if c.stage == "output"])
def test_output_cases_are_pii_redactions(case: AttackCase):
    assert case.category == "pii"
    assert case.expect in ("redact", "block")


def test_cases_are_immutable():
    with pytest.raises(AttributeError):
        CASES[0].payload = "changed"  # type: ignore[misc]
