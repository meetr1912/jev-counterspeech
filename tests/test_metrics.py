"""Hand-checked metric fixtures. Every expected value is derived by hand below."""

import math

import pytest

from jev_counterspeech.metrics import (
    brier_score,
    cross_entropy,
    expected_calibration_error,
    log_loss,
    multiclass_brier,
    reliability_svg,
    reliability_table,
)


def test_brier_exact_on_perfect_predictions():
    assert brier_score([(1, 1), (0, 0)]) == 0.0


def test_brier_half_on_a_coin_flip():
    # ((0.5-1)^2 + (0.5-0)^2) / 2 = 0.25
    assert brier_score([(0.5, 1), (0.5, 0)]) == 0.25


def test_ece_hand_fixture():
    # bin [0.2,0.3): preds 0.2,0.3 -> mean 0.25, rate 0.0 ; weight 1/2 -> 0.125
    # bin [0.8,0.9): preds 0.8,0.9 -> mean 0.85, rate 1.0 ; weight 1/2 -> 0.075
    # ECE = 0.075 + 0.125 = 0.2
    pairs = [(0.9, 1), (0.8, 1), (0.3, 0), (0.2, 0)]
    assert expected_calibration_error(pairs) == pytest.approx(0.2)


def test_reliability_table_counts_sum_to_n():
    pairs = [(0.9, 1), (0.8, 1), (0.3, 0), (0.2, 0)]
    table = reliability_table(pairs)
    assert len(table) == 10
    assert sum(row["count"] for row in table) == len(pairs)


def test_multiclass_brier_one_hot_fixture():
    # pred {a:0.7,b:0.3} truth a -> (0.7-1)^2 + (0.3-0)^2 = 0.18
    dists = [({"a": 0.7, "b": 0.3}, {"a": 1.0, "b": 0.0})]
    assert multiclass_brier(dists) == pytest.approx(0.18)


def test_cross_entropy_one_hot_fixture():
    # -log(0.7) = 0.356675...
    dists = [({"a": 0.7, "b": 0.3}, {"a": 1.0, "b": 0.0})]
    assert cross_entropy(dists) == pytest.approx(-math.log(0.7))


def test_reliability_svg_empty_is_well_formed():
    svg = reliability_svg([])
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_empty_inputs_do_not_crash():
    assert brier_score([]) == 0.0
    assert expected_calibration_error([]) == 0.0
    assert log_loss([]) == 0.0
    assert reliability_table([]) == []
    assert multiclass_brier([]) == 0.0
    assert cross_entropy([]) == 0.0
    assert reliability_svg([]).startswith("<svg")
