"""Shared fixtures for the jev-counterspeech test suite."""

from __future__ import annotations

import pytest

from jev_counterspeech.data import load_examples
from jev_counterspeech.schemas import Triage
from jev_counterspeech.stub import StubJudge


def _make_triage(**overrides) -> Triage:
    """Build a valid, draftable-by-default :class:`Triage`; overrides win."""

    data = {
        "post_id": "p",
        "hateful": 0.9,
        "targets_protected_group": 0.9,
        "has_slur": 0.0,
        "severity_dist": {"0": 0.0, "1": 0.0, "2": 0.2, "3": 0.7, "4": 0.1},
        "severity": 3.0,
        "category": "stereotype",
        "category_probs": {
            "none": 0.0,
            "slur": 0.0,
            "stereotype": 0.8,
            "dehumanization": 0.1,
            "othering": 0.05,
            "threat": 0.05,
        },
        "handling": "reply",
        "handling_probs": {"ignore": 0.05, "report": 0.05, "reply": 0.8, "human_review": 0.1},
        "confidence": 0.8,
        "answers": {},
        "meta": {},
    }
    data.update(overrides)
    return Triage(**data)


@pytest.fixture
def examples():
    return load_examples(seed=7, limit=24)


@pytest.fixture
def judge():
    return StubJudge("calibrated", seed=0)


@pytest.fixture
def results_dir(tmp_path):
    return tmp_path / "results"


@pytest.fixture
def make_triage():
    return _make_triage
