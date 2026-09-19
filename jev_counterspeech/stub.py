"""Deterministic, no-network judge used by CI and offline runs.

The live pipeline talks to Jev over the network; CI has no key, so the default
path is this stub. It implements the same call shape (``triage`` and ``rank``)
and is *genuinely calibrated*, which is what makes the calibration report and its
"teeth" tests meaningful:

* ``calibrated`` (default) emits the example's true generative probabilities:
  ``hateful = example.p_hateful`` and so on. A borderline example (``p`` near
  ``0.5``) is reported with low confidence; a decisive one with high confidence.
* ``oracle`` returns exact one-hot / 0-1 answers matching ``example.label_*`` and
  therefore scores a perfect Brier of 0. It is the anchor that the scoring
  pipeline is wired correctly.
* ``overconfident`` keeps the calibrated ranking and argmax labels but sharpens
  every probability toward 0/1 (``p -> p**2 / (p**2 + (1-p)**2)``) and then adds a
  positive over-prediction bias. The bias matters: sharpening a corpus whose
  labels are pinned by profile can *lower* ECE, so the bias is what reliably makes
  the stub score a higher ECE than ``calibrated`` (the teeth test). This mirrors
  the ``miscalibrated`` stub in ``jev-arena``.

Confidence formula (monotone in decisiveness, so the gate has teeth)::

    d    = |2 * p_hateful - 1|              # 0 at the decision boundary, 1 at the extremes
    conf = 0.35 + 0.5 * d                   # borderline -> 0.35, decisive -> 0.85
    conf += 0.05 * (2 * label_hateful - 1) * d   # small direction adjustment
    confidence = clamp(conf, 0.0, 0.98)

A borderline example (``d = 0``) always yields ``0.35 < 0.65`` (the default gate
threshold), while a decisive one yields well above the gate. ``handling_probs``
is constructed so that its maximum equals ``confidence``, keeping the report and
the gate consistent.

The stub is deterministic given ``(mode, seed)`` and never opens a socket.
"""

from __future__ import annotations

import math
import random

from .schemas import (
    CATEGORIES,
    DIMENSIONS,
    HANDLING,
    QUALITY_CRITERIA,
    SEVERITY_CRITERIA,
    Candidate,
    Example,
    Ranking,
    Triage,
)

STUB_MODES = ("calibrated", "overconfident", "oracle")

#: Fixed temperature for the category softmax (lower = more concentrated).
CATEGORY_TEMPERATURE = 0.3
#: Gaussian spread, in severity grades, for the severity distribution.
SEVERITY_SPREAD = 0.9
#: Softmax temperature turning per-candidate dimension scores into probabilities.
DIMENSION_TEMPERATURE = 0.15
#: Softmax temperature turning overall quality into ``best_probs``.
RANK_TEMPERATURE = 0.2
#: Gaussian spread, in quality grades, for each candidate's quality distribution.
QUALITY_SPREAD = 0.3
#: Exponent for the overconfident stub's probability sharpening.
SHARPNESS = 2.0
#: Positive bias the overconfident stub adds after sharpening. Sharpening alone
#: can *reduce* ECE on a corpus whose labels are pinned by profile, so the bias
#: guarantees the over-prediction that makes the teeth test meaningful.
OVERCONFIDENT_BIAS = 0.2

#: Per-strategy scores on each ranking dimension. ``empathy_question`` and
#: ``shared_norm`` are preferred; ``myth_bust`` is penalized on ``backfire_safety``.
STRATEGY_SCORES: dict[str, dict[str, float]] = {
    "empathy_question": {
        "de_escalation": 0.92,
        "humanization": 0.88,
        "factual_grounding": 0.62,
        "backfire_safety": 0.90,
    },
    "shared_norm": {
        "de_escalation": 0.86,
        "humanization": 0.82,
        "factual_grounding": 0.70,
        "backfire_safety": 0.92,
    },
    "correct_record": {
        "de_escalation": 0.70,
        "humanization": 0.66,
        "factual_grounding": 0.94,
        "backfire_safety": 0.74,
    },
    "invite_dialogue": {
        "de_escalation": 0.84,
        "humanization": 0.74,
        "factual_grounding": 0.55,
        "backfire_safety": 0.86,
    },
    "myth_bust": {
        "de_escalation": 0.52,
        "humanization": 0.58,
        "factual_grounding": 0.90,
        "backfire_safety": 0.30,
    },
}

DEFAULT_STRATEGY_SCORES: dict[str, float] = {dimension: 0.60 for dimension in DIMENSIONS}

DIMENSION_WEIGHTS: dict[str, float] = {
    "de_escalation": 0.30,
    "humanization": 0.25,
    "factual_grounding": 0.20,
    "backfire_safety": 0.25,
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _softmax(weights: dict[str, float], temperature: float) -> dict[str, float]:
    """Numerically stable softmax over ``weights`` at a positive ``temperature``."""

    if not weights:
        return {}
    if temperature <= 0.0:
        raise ValueError("temperature must be positive")
    scaled = {key: value / temperature for key, value in weights.items()}
    top = max(scaled.values())
    exps = {key: math.exp(value - top) for key, value in scaled.items()}
    total = sum(exps.values())
    return {key: value / total for key, value in exps.items()}


def _sharpen_prob(probability: float, sharpness: float = SHARPNESS) -> float:
    """Push a binary probability toward 0/1 while fixing 0, 0.5, and 1."""

    if probability <= 0.0:
        return 0.0
    if probability >= 1.0:
        return 1.0
    powered = probability**sharpness
    other = (1.0 - probability) ** sharpness
    return powered / (powered + other)


def _overconfident_prob(probability: float) -> float:
    """Sharpen toward 0/1 and add the over-prediction bias; see module docstring."""

    return _clamp(_sharpen_prob(probability) + OVERCONFIDENT_BIAS)


def _sharpen_dist(dist: dict[str, float], sharpness: float = SHARPNESS) -> dict[str, float]:
    """Raise a distribution to a power and renormalize (argmax preserved)."""

    if not dist:
        return {}
    powered = {key: value**sharpness for key, value in dist.items()}
    total = sum(powered.values())
    if total <= 0.0:
        return dict(dist)
    return {key: value / total for key, value in powered.items()}


def _severity_dist(p_severity: float) -> dict[str, float]:
    """A severity distribution centered on the expected grade.

    Keys are positional (``"0".."4"``) because that is the live client's ``_score``
    convention: key ``"i"`` stands for grade ``i + 1``.
    """

    center = _clamp(p_severity, 1.0, 5.0)
    logits = {
        str(index): -0.5 * ((((index + 1) - center) / SEVERITY_SPREAD) ** 2)
        for index in range(len(SEVERITY_CRITERIA))
    }
    top = max(logits.values())
    exps = {key: math.exp(value - top) for key, value in logits.items()}
    total = sum(exps.values())
    return {key: value / total for key, value in exps.items()}


def severity_value(dist: dict[str, float]) -> float:
    """Expected 1..5 severity value of a positional severity distribution."""

    return sum((index + 1) * dist[str(index)] for index in range(len(SEVERITY_CRITERIA)))


def _category_probs(label: str, temperature: float = CATEGORY_TEMPERATURE) -> dict[str, float]:
    weights = {category: (1.0 if category == label else 0.0) for category in CATEGORIES}
    return _softmax(weights, temperature)


def _confidence(p_hateful: float, label_hateful: int) -> float:
    """Monotone decisiveness confidence; see the module docstring."""

    distance = abs(2.0 * _clamp(p_hateful) - 1.0)
    confidence = 0.35 + 0.5 * distance
    confidence += 0.05 * (2.0 * int(label_hateful) - 1.0) * distance
    return _clamp(confidence, 0.0, 0.98)


def _handling_probs(label: str, confidence: float) -> dict[str, float]:
    """Concentrate ``1 - confidence`` over the non-chosen handling options.

    The chosen option keeps exactly ``confidence``, so ``max(handling_probs)``
    reproduces the gate statistic.
    """

    others = (1.0 - confidence) / (len(HANDLING) - 1) if len(HANDLING) > 1 else 0.0
    return {handling: (confidence if handling == label else others) for handling in HANDLING}


def _quality_dist(quality: float) -> dict[str, float]:
    """A positional distribution over ``QUALITY_CRITERIA`` centered on ``quality``.

    Key ``"i"`` is criterion ``i`` (worst ``"0"`` -> best), matching the live client.
    """

    if not QUALITY_CRITERIA:
        return {}
    last = len(QUALITY_CRITERIA) - 1
    logits = {}
    for index in range(len(QUALITY_CRITERIA)):
        position = index / last if last else 0.0
        logits[str(index)] = -0.5 * (((position - quality) / QUALITY_SPREAD) ** 2)
    top = max(logits.values())
    exps = {criterion: math.exp(value - top) for criterion, value in logits.items()}
    total = sum(exps.values())
    return {criterion: value / total for criterion, value in exps.items()}


class StubJudge:
    """Offline probability source implementing the live judge's call shape."""

    def __init__(self, mode: str = "calibrated", seed: int = 0) -> None:
        if mode not in STUB_MODES:
            raise ValueError(f"unknown stub mode {mode!r}; choose from {STUB_MODES}")
        self.mode = mode
        self.seed = seed
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------ #
    # Triage
    # ------------------------------------------------------------------ #

    def triage(self, example: Example) -> Triage:
        if self.mode == "oracle":
            return self._triage_oracle(example)
        calibrated = self._triage_calibrated(example)
        if self.mode == "overconfident":
            return self._overtrust(calibrated)
        return calibrated

    def _triage_calibrated(self, example: Example) -> Triage:
        hateful = _clamp(float(example.p_hateful))
        targets = _clamp(float(example.p_targets_group))
        has_slur = _clamp(float(example.p_has_slur))
        severity_dist = _severity_dist(float(example.p_severity))
        category_probs = _category_probs(example.label_category)
        confidence = _confidence(hateful, example.label_hateful)
        handling_probs = _handling_probs(example.label_handling, confidence)
        category = max(category_probs, key=category_probs.get)
        handling = max(handling_probs, key=handling_probs.get)
        return self._build(
            example,
            hateful=hateful,
            targets=targets,
            has_slur=has_slur,
            severity_dist=severity_dist,
            category_probs=category_probs,
            category=category,
            handling_probs=handling_probs,
            handling=handling,
            confidence=confidence,
        )

    def _triage_oracle(self, example: Example) -> Triage:
        last = len(SEVERITY_CRITERIA) - 1
        severity_index = int(example.label_severity) - 1
        if not 0 <= severity_index <= last:
            severity_index = min(
                range(len(SEVERITY_CRITERIA)),
                key=lambda index: abs((index + 1) - float(example.label_severity)),
            )
        severity_dist = {
            str(index): (1.0 if index == severity_index else 0.0)
            for index in range(len(SEVERITY_CRITERIA))
        }
        category_probs = {
            category: (1.0 if category == example.label_category else 0.0) for category in CATEGORIES
        }
        return self._build(
            example,
            hateful=float(example.label_hateful),
            targets=float(example.label_targets_protected_group),
            has_slur=float(example.label_has_slur),
            severity_dist=severity_dist,
            category_probs=category_probs,
            category=example.label_category,
            handling_probs=_handling_probs(example.label_handling, 1.0),
            handling=example.label_handling,
            confidence=1.0,
        )

    def _overtrust(self, calibrated: Triage) -> Triage:
        handling = calibrated.handling
        handling_probs = _sharpen_dist(calibrated.handling_probs)
        severity_dist = _sharpen_dist(calibrated.severity_dist)
        return Triage(
            post_id=calibrated.post_id,
            hateful=_overconfident_prob(calibrated.hateful),
            targets_protected_group=_overconfident_prob(calibrated.targets_protected_group),
            has_slur=_overconfident_prob(calibrated.has_slur),
            severity_dist=severity_dist,
            severity=severity_value(severity_dist),
            category=calibrated.category,
            category_probs=_sharpen_dist(calibrated.category_probs),
            handling=handling,
            handling_probs=handling_probs,
            confidence=_clamp(max(handling_probs.values())),
            answers={
                "hateful": _overconfident_prob(calibrated.hateful),
                "targets_protected_group": _overconfident_prob(calibrated.targets_protected_group),
                "has_slur": _overconfident_prob(calibrated.has_slur),
                "severity": severity_value(severity_dist),
                "category": calibrated.category,
                "handling": handling,
            },
            meta={"mode": self.mode, "offline": True, "seed": self.seed},
        )

    def _build(
        self,
        example: Example,
        *,
        hateful: float,
        targets: float,
        has_slur: float,
        severity_dist: dict[str, float],
        category_probs: dict[str, float],
        category: str,
        handling_probs: dict[str, float],
        handling: str,
        confidence: float,
    ) -> Triage:
        severity = severity_value(severity_dist)
        return Triage(
            post_id=example.id,
            hateful=hateful,
            targets_protected_group=targets,
            has_slur=has_slur,
            severity_dist=severity_dist,
            severity=severity,
            category=category,
            category_probs=category_probs,
            handling=handling,
            handling_probs=handling_probs,
            confidence=confidence,
            answers={
                "hateful": hateful,
                "targets_protected_group": targets,
                "has_slur": has_slur,
                "severity": severity,
                "category": category,
                "handling": handling,
            },
            meta={"mode": self.mode, "offline": True, "seed": self.seed},
        )

    # ------------------------------------------------------------------ #
    # Ranking
    # ------------------------------------------------------------------ #

    def rank(self, example: Example, candidates: list[Candidate]) -> Ranking:
        if not candidates:
            return Ranking(post_id=example.id, meta={"mode": self.mode, "offline": True})

        scores = {
            candidate.id: STRATEGY_SCORES.get(candidate.strategy, DEFAULT_STRATEGY_SCORES)
            for candidate in candidates
        }
        ids = list(scores)

        dimensions: dict[str, dict[str, float]] = {}
        for dimension in DIMENSIONS:
            weights = {cid: scores[cid].get(dimension, 0.5) for cid in ids}
            dimensions[dimension] = _softmax(weights, DIMENSION_TEMPERATURE)

        quality: dict[str, float] = {}
        quality_dists: dict[str, dict[str, float]] = {}
        last = len(QUALITY_CRITERIA) - 1
        for cid in ids:
            aggregate = sum(DIMENSION_WEIGHTS[dim] * scores[cid].get(dim, 0.5) for dim in DIMENSIONS)
            distribution = _quality_dist(_clamp(aggregate))
            quality_dists[cid] = distribution
            expected = sum(index * distribution[str(index)] for index in range(len(QUALITY_CRITERIA)))
            quality[cid] = _clamp(expected / last) if last else 0.0

        best_probs = _softmax({cid: quality[cid] for cid in ids}, RANK_TEMPERATURE)
        best = max(best_probs, key=best_probs.get)
        confidence = _clamp(max(best_probs.values()), 0.0, 0.99)
        return Ranking(
            post_id=example.id,
            quality=quality,
            quality_dists=quality_dists,
            dimensions=dimensions,
            best=best,
            best_probs=best_probs,
            confidence=confidence,
            meta={"mode": self.mode, "offline": True, "seed": self.seed},
        )
