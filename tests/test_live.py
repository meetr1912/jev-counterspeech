"""Live smoke test against TypeSafe. Deselected by default.

Run with:  TYPESAFE_API_KEY=... JEV_LIVE_TESTS=1 uv run pytest -m live -q
"""

import os

import pytest

from jev_counterspeech.data import load_examples
from jev_counterspeech.jev import JevError, LiveJudge
from jev_counterspeech.schemas import CATEGORIES, Triage

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (os.environ.get("TYPESAFE_API_KEY") and os.environ.get("JEV_LIVE_TESTS") == "1"),
        reason="set TYPESAFE_API_KEY and JEV_LIVE_TESTS=1 to run live tests",
    ),
]


def test_live_triage_on_a_benign_post():
    example = next(e for e in load_examples(seed=7) if e.label_category == "none")
    try:
        triage = LiveJudge().triage(example)
    except JevError as error:  # pragma: no cover - network dependent
        pytest.skip(f"live API unavailable: {error}")
    assert isinstance(triage, Triage)
    assert 0.0 <= triage.hateful <= 1.0
    assert triage.category in CATEGORIES
