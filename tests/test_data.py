"""Data generator properties: determinism, coverage, and corpus safety."""

import re

from jev_counterspeech.data import (
    PUBLIC_SAMPLES,
    SYNTHETIC_SOURCE,
    load_examples,
    synthetic_examples,
)
from jev_counterspeech.schemas import CATEGORIES, HANDLING


def test_same_seed_is_deterministic():
    first = load_examples(seed=7)
    second = load_examples(seed=7)
    assert [example.id for example in first] == [example.id for example in second]
    assert [example.text for example in first] == [example.text for example in second]


def test_different_seed_changes_texts():
    assert [e.text for e in load_examples(seed=7)] != [e.text for e in load_examples(seed=8)]


def test_size_and_limit():
    assert len(load_examples(seed=7)) == 120
    assert len(load_examples(seed=7, limit=24)) == 24
    assert load_examples(seed=7, limit=0) == []
    assert len(synthetic_examples(seed=7, n=5)) == 5


def test_all_six_categories_present():
    corpus = load_examples(seed=7)
    assert {example.label_category for example in corpus} == set(CATEGORIES)


def test_labels_and_probabilities_are_in_range():
    for example in load_examples(seed=7):
        assert example.label_hateful in (0, 1)
        assert example.label_targets_protected_group in (0, 1)
        assert example.label_has_slur in (0, 1)
        assert example.label_severity in (1, 2, 3, 4, 5)
        assert example.label_category in CATEGORIES
        assert example.label_handling in HANDLING
        for probability in (example.p_hateful, example.p_targets_group, example.p_has_slur):
            assert 0.0 <= probability <= 1.0
        assert 1.0 <= example.p_severity <= 5.0


def test_every_text_is_non_empty():
    for example in load_examples(seed=7):
        assert example.text.strip()


def test_no_public_samples_are_shipped():
    assert PUBLIC_SAMPLES == ()


def test_source_and_license_on_every_example():
    for example in load_examples(seed=7):
        assert example.source == SYNTHETIC_SOURCE == "synthetic"
        assert example.license == "CC0-1.0"


def test_no_real_slurs_and_no_label_leakage():
    bracketed = re.compile(r"\[[^\]]*\]")
    for example in load_examples(seed=7):
        for token in bracketed.findall(example.text):
            if re.search(r"[Ss][Ll][Uu][Rr]", token):
                assert token == "[SLUR]", token
        for leak in ("p_hateful", "p_targets_group", "p_has_slur", "p_severity", "label_"):
            assert leak not in example.text
