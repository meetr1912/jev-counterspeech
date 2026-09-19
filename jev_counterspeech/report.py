"""Calibration report for jev-counterspeech.

Joins each :class:`~jev_counterspeech.schemas.ReviewedItem` back to its labeled
:class:`~jev_counterspeech.schemas.Example` and measures how well Jev's stated
uncertainty matches the labels. The headline artifact is a reliability diagram
plus Brier / ECE / log loss — a calibration measurement on labeled data, never
an engagement metric.

``write_results`` emits ``results/report.json`` (the machine-readable contract
the review UI consumes), ``results/REPORT.md``, and the SVG/TXT reliability
views.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .metrics import (
    ascii_curve,
    brier_score,
    cross_entropy,
    expected_calibration_error,
    log_loss,
    multiclass_brier,
    reliability_svg,
    reliability_table,
)
from .schemas import DRAFTABLE_ACTION, GATE_ACTIONS, Example, ReviewedItem

_LN2 = math.log(2.0)

RESPONSIBLE_USE_NOTE = (
    "Calibration is measured on labeled examples. Brier/ECE describe how well Jev's stated "
    "uncertainty matches observed outcomes; they are not an engagement or popularity metric and "
    "must not be optimized as one. Every action remains behind a human-review gate."
)

_GUARANTEES: tuple[str, ...] = (
    "Nothing is posted to any network; generated replies only ever land in a local outbox.",
    "A human reviews every draft before anything is sent; the gate can narrow review but never bypass it.",
    "The live judge sees only the post text and an opaque id; labels are used solely for offline measurement.",
    "High-stakes categories are never auto-drafted.",
    "Brier/ECE are reported with the always-0.5 baseline so miscalibration is visible, not hidden.",
)


@dataclass
class CalibrationReport:
    """Aggregate calibration over the reviewed items that have labels."""

    count: int
    brier: float
    ece: float
    log_loss: float
    baseline_brier: float
    per_question: dict
    reliability: list[dict]
    categorical: dict
    severity_mae: float
    severity_brier: float
    label_counts: dict
    note: str
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return exactly the machine-readable fields the UI depends on."""

        return {
            "count": self.count,
            "brier": self.brier,
            "ece": self.ece,
            "log_loss": self.log_loss,
            "baseline_brier": self.baseline_brier,
            "per_question": self.per_question,
            "reliability": self.reliability,
            "categorical": self.categorical,
            "severity_mae": self.severity_mae,
            "severity_brier": self.severity_brier,
            "label_counts": self.label_counts,
            "note": self.note,
        }

    def to_markdown(self) -> str:
        meta = self.meta or {}
        mode = meta.get("mode", "unknown")
        model = meta.get("model", "—")
        examples = meta.get("limit", meta.get("examples", self.count))
        seed = meta.get("seed", "—")

        hateful = self.per_question.get("hateful") or {}
        base_rate = float(hateful.get("base_rate", 0.0)) if self.count else 0.0
        baseline_ece = abs(0.5 - base_rate)

        lines = [
            "# Jev Counterspeech — Calibration Report",
            "",
            f"Mode: **{mode}** · model: **{model}** · examples: **{examples}** · seed: **{seed}**",
            "",
        ]
        if meta.get("stub"):
            lines += [f"Stub: **{meta['stub']}**", ""]
        if meta.get("generated_at"):
            lines += [f"Generated: **{meta['generated_at']}**", ""]

        lines += [
            "## Headline calibration (hateful / noul)",
            "",
            "| Metric | Jev | Always-0.5 |",
            "| --- | ---: | ---: |",
            f"| Brier | {self.brier:.4f} | {self.baseline_brier:.4f} |",
            f"| Log loss | {self.log_loss:.4f} | {_LN2:.4f} |",
            f"| ECE | {self.ece:.4f} | {baseline_ece:.4f} |",
            "",
            f"Events scored: **{self.count}** · labels 0: **{self.label_counts.get(0, 0)}** · "
            f"1: **{self.label_counts.get(1, 0)}**.",
            "",
            "## Per-question calibration",
            "",
            "| question | count | Brier | ECE | Log loss | mean predicted | base rate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for name in ("hateful", "targets_protected_group", "has_slur"):
            row = self.per_question.get(name) or {}
            lines.append(
                f"| {name} | {row.get('count', 0)} | {row.get('brier', 0.0):.4f} | "
                f"{row.get('ece', 0.0):.4f} | {row.get('log_loss', 0.0):.4f} | "
                f"{row.get('mean_predicted', 0.0):.3f} | {row.get('base_rate', 0.0):.3f} |"
            )

        lines += [
            "",
            "## Categorical calibration (choice questions)",
            "",
            "| question | count | multiclass Brier | cross-entropy | accuracy |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for name in ("category", "handling"):
            row = self.categorical.get(name) or {}
            lines.append(
                f"| {name} | {row.get('count', 0)} | {row.get('multiclass_brier', 0.0):.4f} | "
                f"{row.get('cross_entropy', 0.0):.4f} | {row.get('accuracy', 0.0):.3f} |"
            )

        lines += [
            "",
            "## Severity",
            "",
            f"- Severity MAE: **{self.severity_mae:.4f}** (scale 1–5)",
            f"- Severity Brier (normalized /5): **{self.severity_brier:.4f}**",
            "",
            "## Reliability table (hateful)",
            "",
            "| bin | mean predicted | empirical | count | gap |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in self.reliability:
            if not row.get("count"):
                continue
            gap = row["mean_predicted"] - row["empirical"]
            lines.append(
                f"| {row.get('bin')} | {row['mean_predicted']:.3f} | {row['empirical']:.3f} | "
                f"{row['count']} | {gap:+.3f} |"
            )

        lines += [
            "",
            "## ASCII calibration curve",
            "",
            "```",
            ascii_curve(self.reliability),
            "```",
            "",
            f"> **Responsible use:** {self.note}",
            "",
        ]
        return "\n".join(lines)


def _binary_summary(pairs: list[tuple[float, float]]) -> dict:
    if not pairs:
        return {
            "count": 0,
            "brier": 0.0,
            "ece": 0.0,
            "log_loss": 0.0,
            "mean_predicted": 0.0,
            "base_rate": 0.0,
        }
    n = len(pairs)
    return {
        "count": n,
        "brier": brier_score(pairs),
        "ece": expected_calibration_error(pairs),
        "log_loss": log_loss(pairs),
        "mean_predicted": sum(p for p, _ in pairs) / n,
        "base_rate": sum(y for _, y in pairs) / n,
    }


def _argmax(dist: dict) -> str:
    if not dist:
        return ""
    return max(dist, key=lambda label: dist[label])


def _predicted_dist(triage, attr: str) -> dict:
    probs = getattr(triage, f"{attr}_probs", None) or {}
    if probs:
        return dict(probs)
    chosen = getattr(triage, attr, "")
    return {chosen: 1.0} if chosen else {}


def _categorical_summary(
    matched: list[tuple[ReviewedItem, Example]],
    attr: str,
    label_attr: str,
) -> dict:
    dists: list[tuple[dict[str, float], dict[str, float]]] = []
    correct = 0
    for item, example in matched:
        truth_label = getattr(example, label_attr)
        truth = {truth_label: 1.0} if truth_label else {}
        pred = _predicted_dist(item.triage, attr)
        dists.append((pred, truth))
        if truth_label and _argmax(pred) == truth_label:
            correct += 1
    n = len(dists)
    return {
        "multiclass_brier": multiclass_brier(dists),
        "cross_entropy": cross_entropy(dists),
        "accuracy": (correct / n) if n else 0.0,
        "count": n,
    }


def build_calibration(examples: list[Example], items: list[ReviewedItem]) -> CalibrationReport:
    """Join ``item.triage`` to its labeled ``Example`` by ``post_id`` and score."""

    by_id = {example.id: example for example in examples}
    matched: list[tuple[ReviewedItem, Example]] = []
    for item in items:
        example = by_id.get(item.post_id)
        if example is not None:
            matched.append((item, example))

    hateful_pairs = [(item.triage.hateful, float(example.label_hateful)) for item, example in matched]

    per_question: dict[str, dict] = {}
    question_specs = {
        "hateful": ("hateful", "label_hateful"),
        "targets_protected_group": ("targets_protected_group", "label_targets_protected_group"),
        "has_slur": ("has_slur", "label_has_slur"),
    }
    for name, (pred_attr, label_attr) in question_specs.items():
        pairs = [(getattr(item.triage, pred_attr), float(getattr(example, label_attr))) for item, example in matched]
        per_question[name] = _binary_summary(pairs)

    categorical = {
        "category": _categorical_summary(matched, "category", "label_category"),
        "handling": _categorical_summary(matched, "handling", "label_handling"),
    }

    severity = [(item.triage.severity, float(example.label_severity)) for item, example in matched]
    severity_mae = sum(abs(pred - truth) for pred, truth in severity) / len(severity) if severity else 0.0
    severity_brier = brier_score([(pred / 5.0, truth / 5.0) for pred, truth in severity])

    label_counts = {0: 0, 1: 0}
    for _, example in matched:
        label = int(example.label_hateful)
        label_counts[label] = label_counts.get(label, 0) + 1

    return CalibrationReport(
        count=len(hateful_pairs),
        brier=brier_score(hateful_pairs),
        ece=expected_calibration_error(hateful_pairs),
        log_loss=log_loss(hateful_pairs),
        baseline_brier=brier_score([(0.5, truth) for _, truth in hateful_pairs]),
        per_question=per_question,
        reliability=reliability_table(hateful_pairs),
        categorical=categorical,
        severity_mae=severity_mae,
        severity_brier=severity_brier,
        label_counts=label_counts,
        note=RESPONSIBLE_USE_NOTE,
    )


def _md_cell(value: object) -> str:
    """Escape a value for a Markdown table cell."""

    return str(value).replace("|", "\\|").replace("\n", " ")


def _pipeline_markdown(report: CalibrationReport, items: list[ReviewedItem], gate: dict) -> str:
    parts = [report.to_markdown().rstrip(), "", "## Pipeline & gate", ""]
    parts += [
        "| action | count |",
        "| --- | ---: |",
    ]
    for action in GATE_ACTIONS:
        parts.append(f"| {action} | {gate.get(action, 0)} |")
    parts.append(f"| refused (not drafted) | {gate.get('refused', 0)} |")
    parts.append(f"| drafted_items | {gate.get('drafted_items', 0)} |")
    parts += [
        "",
        f"Total reviewed items: **{len(items)}** · gate drafts: **{gate.get('draft', 0)}** · "
        f"refused: **{gate.get('refused', 0)}** · drafted: **{gate.get('drafted_items', 0)}**.",
    ]
    parts += ["", "## Sample reviewed items", ""]
    parts += [
        "| id | category | handling | gate action | #candidates | best candidate |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in items[:10]:
        best = item.ranking.best if item.ranking else ""
        parts.append(
            f"| {_md_cell(item.post_id)} | {_md_cell(item.triage.category)} | "
            f"{_md_cell(item.triage.handling)} | {_md_cell(item.gate.action)} | "
            f"{len(item.candidates)} | {_md_cell(best)} |"
        )
    if not items:
        parts.append("| _(none)_ | | | | 0 | |")
    parts += ["", "## Responsible-use guarantees", ""]
    parts += [f"- {guarantee}" for guarantee in _GUARANTEES]
    parts.append("")
    return "\n".join(parts)


def write_results(
    examples: list[Example],
    items: list[ReviewedItem],
    meta: dict,
    results_dir,
) -> dict[str, str]:
    """Build the calibration report and write all four artifacts. Returns paths."""

    target = Path(results_dir)
    target.mkdir(parents=True, exist_ok=True)

    report = build_calibration(examples, items)
    report.meta = dict(meta or {})

    action_counts = {action: 0 for action in GATE_ACTIONS}
    for item in items:
        action = item.gate.action
        action_counts[action] = action_counts.get(action, 0) + 1

    gate = {
        "draft": action_counts.get("draft", 0),
        "human_review": action_counts.get("human_review", 0),
        "ignore": action_counts.get("ignore", 0),
        "report": action_counts.get("report", 0),
        "refused": sum(1 for item in items if item.gate.action != DRAFTABLE_ACTION),
        "drafted_items": sum(1 for item in items if item.drafted),
    }

    payload = {
        "meta": dict(meta or {}),
        "calibration": report.to_dict(),
        "gate": gate,
        "items": [item.to_dict() for item in items],
    }

    report_json = target / "report.json"
    report_md = target / "REPORT.md"
    svg_path = target / "reliability.svg"
    txt_path = target / "reliability.txt"

    report_json.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    report_md.write_text(_pipeline_markdown(report, items, gate))
    svg_path.write_text(reliability_svg(report.reliability))
    txt_path.write_text(ascii_curve(report.reliability) + "\n")

    return {
        "report_json": str(report_json),
        "report_md": str(report_md),
        "reliability_svg": str(svg_path),
        "reliability_txt": str(txt_path),
    }
