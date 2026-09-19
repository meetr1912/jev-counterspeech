"""The counterspeech pipeline: triage -> gate -> (only if draftable) draft -> rank.

The single most important property of this module is the safety invariant:

    ``draft_candidates`` and ``judge.rank`` are NEVER called for a non-``draft`` gate.

Jev first triages every post, the gate turns that triage into an explicit action, and
only an action of ``"draft"`` unlocks the downstream drafting and ranking steps. Every
other action (``human_review``, ``ignore``, ``report``) stops the pipeline and records a
human-readable refusal note built from the gate's reasons.

Per-post failures are contained so one bad post cannot abort a run:

* a ``JevError`` is systemic (auth, quota, transport) and is re-raised for the CLI to
  report cleanly;
* any other ``RuntimeError`` from triage is fail-closed: the post is kept with a neutral
  placeholder triage and a ``human_review`` gate, so it still reaches a human;
* a ``RuntimeError`` from drafting or ranking leaves the post draftable but with no
  candidates/ranking and a note explaining what failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .data import load_examples
from .drafts import draft_candidates
from .gate import decide_gate
from .jev import JevError, LiveJudge
from .schemas import (
    DEFAULT_GATE_THRESHOLD,
    Candidate,
    Example,
    GateDecision,
    Ranking,
    ReviewedItem,
    Triage,
)
from .stub import StubJudge

#: LiveJudge.rank requires at least this many candidates.
_MIN_RANK_CANDIDATES = 2

#: LiveJudge.rank accepts at most this many candidates.
_MAX_RANK_CANDIDATES = 8


@dataclass
class RunResult:
    """Everything one pipeline run produced, ready for the report and the UI."""

    examples: list[Example]
    items: list[ReviewedItem]
    meta: dict


def make_judge(offline: bool, stub: str = "calibrated", seed: int = 0):
    """Return the offline stub by default, or the live Jev client when asked."""

    if offline:
        return StubJudge(mode=stub, seed=seed)
    return LiveJudge()


def summarize(items: list[ReviewedItem]) -> dict:
    """Count gate actions and how many posts were actually drafted/refused."""

    counts = {
        "draft": 0,
        "human_review": 0,
        "ignore": 0,
        "report": 0,
        "refused": 0,
        "drafted_items": 0,
    }
    for item in items:
        action = item.gate.action
        if action in counts:
            counts[action] += 1
        if not item.gate.should_draft:
            counts["refused"] += 1
        if item.drafted:
            counts["drafted_items"] += 1
    return counts


def _fail_closed_triage(post_id: str, error: str) -> Triage:
    """A neutral placeholder so a post whose triage failed still reaches a human."""

    return Triage(
        post_id=post_id,
        hateful=0.0,
        targets_protected_group=0.0,
        has_slur=0.0,
        severity_dist={},
        severity=0.0,
        category="none",
        category_probs={},
        handling="human_review",
        handling_probs={},
        confidence=0.0,
        meta={"failed": True, "error": error},
    )


def _append_note(existing: str, addition: str) -> str:
    return f"{existing}; {addition}" if existing else addition


def run(
    *,
    offline: bool = True,
    stub: str = "calibrated",
    seed: int = 7,
    limit: int = 24,
    threshold: float = DEFAULT_GATE_THRESHOLD,
    draft_mode: str = "template",
    include_public: bool = False,
) -> RunResult:
    """Triage, gate, and (only when permitted) draft and rank every loaded example."""

    judge = make_judge(offline, stub=stub, seed=seed)
    examples = load_examples(seed=seed, limit=limit, include_public=include_public)
    items: list[ReviewedItem] = []

    for example in examples:
        try:
            triage = judge.triage(example)
        except JevError:
            # Systemic failure (auth/quota/transport): let the CLI report it cleanly.
            raise
        except RuntimeError as error:
            reason = f"triage failed: {error}"
            gate = GateDecision(action="human_review", reasons=[reason], threshold=threshold)
            items.append(
                ReviewedItem(
                    post_id=example.id,
                    text=example.text,
                    triage=_fail_closed_triage(example.id, str(error)),
                    gate=gate,
                    candidates=[],
                    ranking=None,
                    drafted=False,
                    note=reason,
                )
            )
            continue

        gate = decide_gate(triage, threshold)

        candidates: list[Candidate] = []
        ranking: Ranking | None = None
        note = ""

        if gate.should_draft:
            # SAFETY: we are inside `gate.should_draft`; nothing below runs otherwise.
            try:
                candidates = draft_candidates(example, triage, mode=draft_mode)
            except JevError:
                raise
            except RuntimeError as error:
                candidates = []
                note = _append_note(note, f"drafting failed: {error}")

            if len(candidates) < _MIN_RANK_CANDIDATES or len(candidates) > _MAX_RANK_CANDIDATES:
                note = _append_note(
                    note,
                    f"ranking skipped: {len(candidates)} candidates (need "
                    f"{_MIN_RANK_CANDIDATES}..{_MAX_RANK_CANDIDATES})",
                )
            else:
                try:
                    ranking = judge.rank(example, candidates)
                except JevError:
                    raise
                except RuntimeError as error:
                    ranking = None
                    note = _append_note(note, f"ranking failed: {error}")
        else:
            note = "; ".join(gate.reasons)

        items.append(
            ReviewedItem(
                post_id=example.id,
                text=example.text,
                triage=triage,
                gate=gate,
                candidates=candidates,
                ranking=ranking,
                drafted=gate.should_draft,
                note=note,
            )
        )

    meta = {
        "mode": "offline" if offline else "live",
        "stub": None if not offline else stub,
        "seed": seed,
        "limit": limit,
        "threshold": threshold,
        "draft_mode": draft_mode,
        "include_public": include_public,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": summarize(items),
        "examples": len(examples),
    }
    return RunResult(examples=examples, items=items, meta=meta)
