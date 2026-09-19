"""Stub behaviour: calibrated exposes label probabilities, oracle is perfect."""

import pytest

from jev_counterspeech.data import load_examples
from jev_counterspeech.drafts import TEMPLATE_STRATEGIES
from jev_counterspeech.metrics import brier_score, expected_calibration_error
from jev_counterspeech.schemas import DEFAULT_GATE_THRESHOLD, DIMENSIONS, Candidate
from jev_counterspeech.stub import StubJudge, severity_value


def test_calibrated_exposes_example_probabilities(examples, judge):
    for example in examples:
        triage = judge.triage(example)
        assert triage.hateful == example.p_hateful
        assert triage.targets_protected_group == example.p_targets_group
        assert triage.has_slur == example.p_has_slur
        assert triage.severity == severity_value(triage.severity_dist)
        assert triage.severity == pytest.approx(example.p_severity, abs=0.5)


def test_borderline_examples_get_low_confidence(judge):
    borderline = [e for e in load_examples(seed=7) if 0.42 <= e.p_hateful <= 0.62]
    assert borderline
    for example in borderline:
        assert judge.triage(example).confidence < DEFAULT_GATE_THRESHOLD


def test_oracle_scores_a_perfect_brier():
    corpus = load_examples(seed=7)
    oracle = StubJudge("oracle", seed=0)
    pairs = [(oracle.triage(example).hateful, float(example.label_hateful)) for example in corpus]
    assert brier_score(pairs) == 0.0


def test_overconfident_has_worse_calibration_than_calibrated():
    corpus = load_examples(seed=7)
    calibrated = StubJudge("calibrated", seed=0)
    overconfident = StubJudge("overconfident", seed=0)
    calibrated_pairs = [(calibrated.triage(e).hateful, float(e.label_hateful)) for e in corpus]
    overconfident_pairs = [(overconfident.triage(e).hateful, float(e.label_hateful)) for e in corpus]
    assert expected_calibration_error(overconfident_pairs) > expected_calibration_error(calibrated_pairs)


def test_rank_returns_a_complete_ranking(examples, judge):
    example = examples[0]
    candidates = [
        Candidate(id=f"c{i + 1}", text=f"reply {i + 1}", strategy=TEMPLATE_STRATEGIES[i])
        for i in range(len(TEMPLATE_STRATEGIES))
    ]
    ranking = judge.rank(example, candidates)
    ids = {candidate.id for candidate in candidates}
    assert set(ranking.quality) == ids
    assert all(0.0 <= quality <= 1.0 for quality in ranking.quality.values())
    for dimension in DIMENSIONS:
        assert dimension in ranking.dimensions
        assert sum(ranking.dimensions[dimension].values()) == pytest.approx(1.0)
    assert ranking.best in ids


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        StubJudge("nope")

