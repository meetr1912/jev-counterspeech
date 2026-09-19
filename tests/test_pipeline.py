"""The pipeline safety invariant: drafting and ranking only run for a 'draft' gate."""

import pytest

from jev_counterspeech import pipeline
from jev_counterspeech.schemas import Candidate, Ranking
from jev_counterspeech.stub import StubJudge


class _Spy:
    def __init__(self, result):
        self.calls = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


def _candidates():
    return [
        Candidate(id="c1", text="one", strategy="empathy_question"),
        Candidate(id="c2", text="two", strategy="shared_norm"),
    ]


def _forced_run(monkeypatch, triage):
    judge = StubJudge("calibrated", seed=0)
    monkeypatch.setattr(judge, "triage", lambda example: triage)
    rank_spy = _Spy(Ranking(post_id="p"))
    monkeypatch.setattr(judge, "rank", rank_spy)
    draft_spy = _Spy(_candidates())
    monkeypatch.setattr(pipeline, "draft_candidates", draft_spy)
    monkeypatch.setattr(pipeline, "make_judge", lambda *args, **kwargs: judge)
    result = pipeline.run(offline=True, limit=3)
    return result, draft_spy, rank_spy


def test_pipeline_never_drafts_or_ranks_a_high_stakes_post(monkeypatch, make_triage):
    forced = make_triage(category="threat", confidence=0.1)
    result, draft_spy, rank_spy = _forced_run(monkeypatch, forced)

    assert draft_spy.calls == []
    assert rank_spy.calls == []
    assert len(result.items) == 3
    for item in result.items:
        assert item.candidates == []
        assert item.ranking is None
        assert item.drafted is False


def test_pipeline_drafts_and_ranks_when_the_gate_allows(monkeypatch, make_triage):
    forced = make_triage()
    result, draft_spy, rank_spy = _forced_run(monkeypatch, forced)

    assert len(draft_spy.calls) == 3
    assert len(rank_spy.calls) == 3
    for item in result.items:
        assert item.candidates
        assert item.ranking is not None
        assert item.drafted is True


def test_run_limit_and_summary_are_consistent():
    result = pipeline.run(offline=True, limit=6)
    assert len(result.items) == 6
    assert result.meta["examples"] == 6
    assert result.meta["counts"] == pipeline.summarize(result.items)


def test_real_run_keeps_non_draft_items_empty():
    result = pipeline.run(offline=True, limit=24)
    for item in result.items:
        assert item.drafted == item.gate.should_draft
        if not item.gate.should_draft:
            assert item.candidates == []
            assert item.ranking is None


class _FakeJudge:
    """A judge with a fixed triage outcome and a spy for ``rank``."""

    def __init__(self, triage, rank_spy):
        self._triage = triage
        self.rank = rank_spy

    def triage(self, example):
        return self._triage


def _run_one(monkeypatch, triage):
    """Run the pipeline on one example with spies around drafting and ranking."""

    draft_spy = _Spy(_candidates())
    rank_spy = _Spy(Ranking(post_id="p", best="c1", confidence=0.9))
    judge = _FakeJudge(triage, rank_spy)
    monkeypatch.setattr(pipeline, "draft_candidates", draft_spy)
    monkeypatch.setattr(pipeline, "make_judge", lambda *args, **kwargs: judge)
    result = pipeline.run(offline=True, limit=1)
    assert len(result.items) == 1
    return result.items[0], draft_spy, rank_spy


_REFUSED_TRIAGES = [
    pytest.param({"category": "threat", "confidence": 0.1}, id="threat_category"),
    pytest.param({"hateful": 0.8, "targets_protected_group": 0.1}, id="targets_individual"),
    pytest.param({"severity": 4.0, "category": "slur", "handling": "reply"}, id="severity_4"),
    pytest.param({"severity": 5.0}, id="severity_5"),
    pytest.param({"confidence": 0.5}, id="low_confidence"),
    pytest.param({"handling": "human_review"}, id="handling_human_review"),
    pytest.param({"handling": "reply", "hateful": 0.3}, id="reply_but_not_hateful"),
]


@pytest.mark.parametrize("overrides", _REFUSED_TRIAGES)
def test_pipeline_never_drafts_or_ranks_when_gate_refuses(monkeypatch, make_triage, overrides):
    triage = make_triage(**overrides)

    item, draft_spy, rank_spy = _run_one(monkeypatch, triage)

    assert draft_spy.calls == []
    assert rank_spy.calls == []
    assert item.candidates == []
    assert item.ranking is None
    assert item.drafted is False


def test_pipeline_drafts_and_ranks_for_a_clean_case(monkeypatch, make_triage):
    triage = make_triage(
        hateful=0.9,
        targets_protected_group=0.9,
        severity=3.0,
        handling="reply",
        confidence=0.9,
    )

    item, draft_spy, rank_spy = _run_one(monkeypatch, triage)

    assert item.drafted is True
    assert len(item.candidates) >= 2
    assert item.ranking is not None
    assert len(draft_spy.calls) == 1
    assert len(rank_spy.calls) == 1
