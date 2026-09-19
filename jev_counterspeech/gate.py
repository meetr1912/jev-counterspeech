"""The explicit, testable confidence/safety gate.

The gate is the only place allowed to turn a probabilistic :class:`Triage` into an
action. It is deliberately a tiny, ordered, side-effect-free function so the
safety policy can be read, reasoned about, and unit-tested without a network call.

Policy: **fail closed.** Uncertainty and high stakes both route to a human. A
``"draft"`` is returned only when every earlier check has passed -- the content is
not a high-stakes category, does not single out an individual, is not severity 4
or 5, Jev is confident, and the recommended handling is a reply to group-targeted
hate. Even then, drafting is a proposal: a human still reviews and "sends".

Severity 4 (a slur or dehumanizing language) is deliberately treated as
high-stakes and is never auto-drafted, even when Jev is confident. This is a
conscious safety-over-capability choice: the pipeline will only *propose* text for
milder, group-directed stereotype/othering content, and a person still has to
approve it.
"""

from __future__ import annotations

from .schemas import DEFAULT_GATE_THRESHOLD, HIGH_STAKES_CATEGORIES, GateDecision, Triage


def is_high_stakes(triage: Triage) -> bool:
    """True when the post is high-stakes regardless of Jev's confidence.

    Covers the first three gate rules: a high-stakes category, hate aimed at an
    individual rather than a protected group, or severity 4-5 (a slur or
    dehumanization). These are the cases where a confident-but-wrong model would
    do the most harm.
    """

    if triage.category in HIGH_STAKES_CATEGORIES:
        return True
    if triage.targets_individual:
        return True
    return triage.severity >= 4


def decide_gate(triage: Triage, threshold: float = DEFAULT_GATE_THRESHOLD) -> GateDecision:
    """Apply the ordered gate rules and return the resulting :class:`GateDecision`.

    Rules are evaluated in order and the first match wins:

    1. High-stakes category -> human review.
    2. Targets an individual, not a protected group -> human review.
    3. Severity 4-5 (slur/dehumanization/threat) -> human review.
    4. Confidence below ``threshold`` -> human review (uncertainty fails closed).
    5. Handling ``ignore`` -> ignore.
    6. Handling ``report`` -> report.
    7. Handling ``human_review`` -> human review.
    8. Handling ``reply`` without a hateful read -> human review.
    9. Otherwise -> draft (still human-reviewed before anything is sent).
    """

    if triage.category in HIGH_STAKES_CATEGORIES:
        return GateDecision("human_review", ["category=threat is high-stakes"], threshold)
    if triage.targets_individual:
        return GateDecision("human_review", ["targets an individual, not a protected group"], threshold)
    if triage.severity >= 4:
        return GateDecision("human_review", ["severity >= 4 (slur/dehumanization) is high-stakes"], threshold)
    if triage.confidence < threshold:
        return GateDecision(
            "human_review",
            [f"confidence {triage.confidence:.2f} < threshold {threshold:.2f}"],
            threshold,
        )
    if triage.handling == "ignore":
        return GateDecision("ignore", ["handling=ignore"], threshold)
    if triage.handling == "report":
        return GateDecision("report", ["handling=report"], threshold)
    if triage.handling == "human_review":
        return GateDecision("human_review", ["handling=human_review"], threshold)
    if triage.handling == "reply" and not triage.is_hateful:
        return GateDecision(
            "human_review",
            ["handling=reply but hateful probability below 0.5"],
            threshold,
        )
    return GateDecision("draft", ["confident, group-targeted, reply-worthy"], threshold)
