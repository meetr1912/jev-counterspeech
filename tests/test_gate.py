"""The gate is the safety core: it must fail closed for every high-stakes case."""

from jev_counterspeech.gate import decide_gate, is_high_stakes
from jev_counterspeech.schemas import DEFAULT_GATE_THRESHOLD


def test_gate_refuses_to_draft_for_low_confidence_and_high_stakes(make_triage):
    threat = make_triage(category="threat", confidence=0.9)
    individual = make_triage(hateful=0.8, targets_protected_group=0.1, confidence=0.9)
    severity_four = make_triage(severity=4, confidence=0.9)
    severity_five = make_triage(severity=5, confidence=0.9)
    low_confidence = make_triage(confidence=0.5)

    for triage in (threat, individual, severity_four, severity_five, low_confidence):
        decision = decide_gate(triage)
        assert decision.action == "human_review"
        assert decision.should_draft is False

    assert DEFAULT_GATE_THRESHOLD == 0.65
    assert decide_gate(low_confidence).threshold == DEFAULT_GATE_THRESHOLD

    clean = make_triage(
        hateful=0.9,
        targets_protected_group=0.9,
        severity=3,
        handling="reply",
        confidence=0.9,
    )
    assert decide_gate(clean).action == "draft"
    assert decide_gate(clean).should_draft is True


def test_is_high_stakes_flags_only_the_high_stakes_cases(make_triage):
    assert is_high_stakes(make_triage(category="threat")) is True
    assert is_high_stakes(make_triage(hateful=0.8, targets_protected_group=0.1)) is True
    assert is_high_stakes(make_triage(severity=4)) is True
    assert is_high_stakes(make_triage(severity=5)) is True
    assert is_high_stakes(make_triage()) is False


def test_handling_maps_to_action(make_triage):
    assert decide_gate(make_triage(handling="ignore")).action == "ignore"
    assert decide_gate(make_triage(handling="report")).action == "report"
    assert decide_gate(make_triage(handling="human_review")).action == "human_review"


def test_rule_eight_reply_without_a_hateful_read_is_human_review(make_triage):
    decision = decide_gate(make_triage(handling="reply", hateful=0.3))
    assert decision.action == "human_review"


def test_custom_threshold_overrides_the_default(make_triage):
    assert decide_gate(make_triage(confidence=0.5), threshold=0.4).action == "draft"
    assert decide_gate(make_triage(confidence=0.7), threshold=0.9).action == "human_review"
