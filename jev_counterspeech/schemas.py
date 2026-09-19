"""Frozen shared types for jev-counterspeech.

Every module imports its vocabulary from here so the triage client, the offline
stub, the gate, the ranking client, the report, and the review UI all agree on
one schema. Keep this file additive: changing a field name breaks the pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# --------------------------------------------------------------------------- #
# Question vocabularies (offered to Jev as typed criteria)
# --------------------------------------------------------------------------- #

#: `choice` category question. "none" means no hateful content was detected.
CATEGORIES: tuple[str, ...] = (
    "none",
    "slur",
    "stereotype",
    "dehumanization",
    "othering",
    "threat",
)

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "none": "No hateful, harassing, or dehumanizing content.",
    "slur": "Contains a slur or slur-like targeted epithet.",
    "stereotype": "Asserts a negative generalization about a protected group.",
    "dehumanization": "Likens a protected group to animals, vermin, disease, or objects.",
    "othering": "Frames a protected group as alien, foreign, or not belonging.",
    "threat": "Calls for, encourages, or celebrates violence or harm.",
}

#: `choice` handling question.
HANDLING: tuple[str, ...] = ("ignore", "report", "reply", "human_review")

HANDLING_DESCRIPTIONS: dict[str, str] = {
    "ignore": "Do not engage; no reply and no report.",
    "report": "Route to platform trust-and-safety; do not reply publicly.",
    "reply": "A respectful counterspeech reply may be appropriate after human review.",
    "human_review": "Uncertain or high-stakes; a human must decide before any action.",
}

#: `score` severity question. Ordered criteria; the answer is a distribution.
SEVERITY_CRITERIA: tuple[str, ...] = ("1", "2", "3", "4", "5")
SEVERITY_DESCRIPTIONS: dict[str, str] = {
    "1": "Not hateful.",
    "2": "Mild bias, no slur, no threat.",
    "3": "Clear hateful generalization or othering.",
    "4": "Slur or dehumanization, no explicit threat.",
    "5": "Explicit threat or call to violence.",
}

#: Categories that are never auto-drafted, regardless of the handling answer.
HIGH_STAKES_CATEGORIES: tuple[str, ...] = ("threat",)

#: Ranking dimensions. Each becomes a `choice` question over the candidate replies.
DIMENSIONS: tuple[str, ...] = (
    "de_escalation",
    "humanization",
    "factual_grounding",
    "backfire_safety",
)

DIMENSION_DESCRIPTIONS: dict[str, str] = {
    "de_escalation": "Lowers the temperature and avoids escalating conflict.",
    "humanization": "Restores the humanity of the targeted group; no dehumanizing framing.",
    "factual_grounding": "Corrects false claims with accurate, verifiable framing.",
    "backfire_safety": (
        "Unlikely to be screenshotted, mocked, or used to recruit (the higher the probability, the safer)."
    ),
}

#: `score` overall-quality question per candidate. Ordered worst -> best.
QUALITY_CRITERIA: tuple[str, ...] = ("harmful", "weak", "neutral", "good", "excellent")

#: Default confidence gate. Below this, Jev's handling answer is not trusted.
DEFAULT_GATE_THRESHOLD = 0.65

#: Gate action vocabulary.
GATE_ACTIONS: tuple[str, ...] = ("draft", "human_review", "ignore", "report")

#: The only action for which the pipeline is allowed to generate candidate drafts.
DRAFTABLE_ACTION = "draft"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Example:
    """One labeled post. ``label_*`` and ``p_*`` are ground truth used ONLY by the
    offline stub, calibration report, and tests. The live judge receives ``text``
    and ``id`` only, never the labels.
    """

    id: str
    text: str
    label_hateful: int
    label_targets_protected_group: int
    label_has_slur: int
    label_severity: int
    label_category: str
    label_handling: str
    p_hateful: float
    p_targets_group: float
    p_has_slur: float
    p_severity: float
    source: str = "synthetic"
    license: str = "CC0-1.0"
    notes: str = ""

    def post(self) -> dict:
        """The only view a live model is allowed to see: text plus an opaque id."""

        return {"id": self.id, "text": self.text}

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Triage / gate
# --------------------------------------------------------------------------- #


@dataclass
class Triage:
    """Validated, normalized read of one post from one fan-out Jev request."""

    post_id: str
    hateful: float
    targets_protected_group: float
    has_slur: float
    severity_dist: dict[str, float]
    severity: float
    category: str
    category_probs: dict[str, float]
    handling: str
    handling_probs: dict[str, float]
    confidence: float
    answers: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    @property
    def is_hateful(self) -> bool:
        return self.hateful >= 0.5

    @property
    def targets_individual(self) -> bool:
        """Hateful but aimed at a person rather than a protected group."""

        return self.hateful >= 0.5 and self.targets_protected_group < 0.5

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateDecision:
    """The explicit, testable decision about whether drafting is permitted."""

    action: str
    reasons: list[str] = field(default_factory=list)
    threshold: float = DEFAULT_GATE_THRESHOLD

    @property
    def should_draft(self) -> bool:
        return self.action == DRAFTABLE_ACTION

    @property
    def requires_human(self) -> bool:
        return self.action in ("human_review", "draft")

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Drafting / ranking
# --------------------------------------------------------------------------- #


@dataclass
class Candidate:
    """A precomputed candidate reply. Jev scores it; it never writes it."""

    id: str
    text: str
    strategy: str
    origin: str = "template"  # "template" | "llm"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ranking:
    """Jev's distributional ranking of the candidate replies."""

    post_id: str
    quality: dict[str, float] = field(default_factory=dict)
    quality_dists: dict[str, dict[str, float]] = field(default_factory=dict)
    dimensions: dict[str, dict[str, float]] = field(default_factory=dict)
    best: str = ""
    best_probs: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewedItem:
    """One post's full journey: triage -> gate -> drafts -> ranking."""

    post_id: str
    text: str
    triage: Triage
    gate: GateDecision
    candidates: list[Candidate] = field(default_factory=list)
    ranking: Ranking | None = None
    drafted: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "text": self.text,
            "triage": self.triage.to_dict(),
            "gate": self.gate.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "ranking": self.ranking.to_dict() if self.ranking else None,
            "drafted": self.drafted,
            "note": self.note,
        }
