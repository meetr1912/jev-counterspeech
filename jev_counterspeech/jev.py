"""Live TypeSafe System One client for jev-counterspeech.

A responsible counterspeech assistant needs a calibrated read of a post *before*
any reply is even considered. This client asks Jev (TypeSafe) two fan-out
questions, each in exactly one ``systemone`` request:

* :meth:`LiveJudge.triage` -- classify one post: hateful, group-targeted, slur,
  ordered severity, category, and handling.
* :meth:`LiveJudge.rank` -- score a small slate of precomputed candidate replies.

Safety posture (why this module looks the way it does):

* Jev **classifies and scores**; it never writes a reply. The model must never see
  the ground-truth labels in :class:`~jev_counterspeech.schemas.Example`, so only
  ``id`` and ``text`` are placed in ``state``.
* Uncertainty fails closed. The gate (:mod:`jev_counterspeech.gate`) routes any
  low-confidence or high-stakes read to a human, so this module returns the whole
  distribution rather than only an argmax.
* No module-level network calls: importing this module must be free of side
  effects. A shared ``httpx`` client is constructed, but no request is issued and
  no key is resolved until a method is called.
* The API key is resolved at call time and is never printed, logged, or persisted.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Callable, TypeVar

import httpx

from .schemas import (
    CATEGORIES,
    CATEGORY_DESCRIPTIONS,
    DIMENSION_DESCRIPTIONS,
    DIMENSIONS,
    HANDLING,
    HANDLING_DESCRIPTIONS,
    QUALITY_CRITERIA,
    SEVERITY_CRITERIA,
    SEVERITY_DESCRIPTIONS,
    Candidate,
    Example,
    Ranking,
    Triage,
)

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CLIENT = httpx.Client(http2=True, timeout=120)
RETRYABLE = {429, 503, 529}

#: Questions asked by :meth:`LiveJudge.triage`, in one request. Keys are the
#: answer identifiers carried back by TypeSafe.
TRIAGE_QUESTIONS: tuple[str, ...] = (
    "hateful",
    "targets_protected_group",
    "has_slur",
    "severity",
    "category",
    "handling",
)

#: Neutral, de-identified task framing. It names no person and asks only for a
#: classification, never for a reply.
TRIAGE_TASK = (
    "Classify one social-media post for hateful, harassing, or dehumanizing "
    "content and recommend the safest handling. Classify the text only: do not "
    "identify, target, or write about any individual, and do not draft a reply."
)

#: Ranking framing. Jev scores precomputed candidates; it never authors one.
RANK_TASK = (
    "Score and rank the candidate counterspeech replies for one post. You are "
    "selecting among precomputed options only: do not write, rewrite, or add any "
    "reply text."
)

#: Safety rules repeated in the request state for both tasks.
SAFETY_RULES: tuple[str, ...] = (
    "Never target, single out, or identify an individual person; judge the content, not people.",
    "Prefer de-escalation and restore the humanity of any targeted group.",
    "Never propose mass, automated, or coordinated replies. Any reply is reviewed by a human first.",
    "When uncertain or when the stakes are high, say so through a flatter distribution.",
)

T = TypeVar("T")


class JevError(RuntimeError):
    """The TypeSafe call failed or returned an unusable answer."""


def load_env_file(path: Path) -> None:
    """Load ``KEY=VALUE`` lines from ``path`` without overwriting existing env.

    Missing files are ignored. Values are only ever placed in ``os.environ``;
    nothing is printed or written back to disk.
    """

    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def ensure_api_key() -> str:
    """Resolve the key without ever printing, logging, or persisting it.

    Order: process environment -> ``<repo>/.env`` -> ``~/jev-ultrafast/.env``. The
    repo's ``.env`` is gitignored and is never created by this tool; the fallback
    file is read at runtime only.
    """

    if not os.environ.get("TYPESAFE_API_KEY"):
        load_env_file(Path(__file__).resolve().parent.parent / ".env")
    if not os.environ.get("TYPESAFE_API_KEY"):
        load_env_file(Path.home() / "jev-ultrafast" / ".env")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise JevError(
            "TYPESAFE_API_KEY is not set (add it to jev-counterspeech/.env or ~/jev-ultrafast/.env, "
            "or export it in the environment)"
        )
    return key


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def _finite_unit(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0.0 <= float(value) <= 1.0


def _answers_object(answers: object, expected: set[str], what: str) -> dict:
    if not isinstance(answers, dict):
        raise JevError(f"{what}: answers was not an object")
    if set(answers) != expected:
        raise JevError(f"{what}: answer keys did not match exactly the offered questions")
    return answers


def _noul(answers: dict, qid: str) -> float:
    answer = answers.get(qid)
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        raise JevError(f"{qid}: missing noul answer")
    value = answer.get("noul")
    if not _finite_unit(value):
        raise JevError(f"{qid}: noul is not a probability in [0, 1]")
    return float(value)


def _distribution(answer: dict, labels: tuple[str, ...], qid: str) -> dict[str, float]:
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(labels):
        raise JevError(f"{qid}: probabilities did not cover exactly the offered criteria")
    if not all(_finite_unit(value) for value in probabilities.values()):
        raise JevError(f"{qid}: returned a non-finite probability")
    total = sum(float(probabilities[label]) for label in labels)
    if abs(total - 1.0) >= 0.02:
        raise JevError(f"{qid}: probabilities did not sum to 1")
    if total <= 0.0:
        raise JevError(f"{qid}: probabilities sum to zero")
    return {label: float(probabilities[label]) / total for label in labels}


def _choice(answers: dict, qid: str, labels: tuple[str, ...]) -> tuple[str, dict[str, float], float]:
    answer = answers.get(qid)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise JevError(f"{qid}: missing choice answer")
    probabilities = _distribution(answer, labels, qid)
    choice = answer.get("choice")
    if choice not in set(labels):
        raise JevError(f"{qid}: choice was not offered")
    confidence = answer.get("confidence")
    if confidence is None:
        confidence = max(probabilities.values())
    elif not _finite_unit(confidence):
        raise JevError(f"{qid}: confidence is not a probability in [0, 1]")
    else:
        confidence = float(confidence)
    return str(choice), probabilities, confidence


def _score(answers: dict, qid: str, criteria: tuple[str, ...]) -> dict[str, float]:
    answer = answers.get(qid)
    if not isinstance(answer, dict) or answer.get("type") != "score":
        raise JevError(f"{qid}: missing score answer")
    return _distribution(answer, tuple(str(i) for i in range(len(criteria))), qid)


# --------------------------------------------------------------------------- #
# Request construction
# --------------------------------------------------------------------------- #


def _severity_instructions() -> str:
    descriptions = "; ".join(f"{label} = {SEVERITY_DESCRIPTIONS[label]}" for label in SEVERITY_CRITERIA)
    return (
        "How severe is the content? Return a probability distribution over the ordered "
        f"criteria ({descriptions}). Answer every criterion with your true probability."
    )


def build_triage_questions() -> dict:
    """All triage heads for one post; sent together in a single request."""

    return {
        "hateful": {
            "type": "noul",
            "instructions": (
                "Does this post contain hateful, harassing, or dehumanizing content? "
                "Answer with your true probability in [0, 1]. Classify only; do not target anyone."
            ),
        },
        "targets_protected_group": {
            "type": "noul",
            "instructions": (
                "Does the post target a protected group rather than a private individual? "
                "Answer with your true probability in [0, 1]."
            ),
        },
        "has_slur": {
            "type": "noul",
            "instructions": (
                "Does the post contain a slur or slur-like targeted epithet? "
                "Answer with your true probability in [0, 1]."
            ),
        },
        "severity": {
            "type": "score",
            "instructions": _severity_instructions(),
            "criteria": list(SEVERITY_CRITERIA),
        },
        "category": {
            "type": "choice",
            "instructions": (
                "Which single category best describes the post? Classify the text; "
                "do not identify or target any individual."
            ),
            "criteria": {label: CATEGORY_DESCRIPTIONS[label] for label in CATEGORIES},
        },
        "handling": {
            "type": "choice",
            "instructions": (
                "What is the safest handling? Prefer de-escalation, never propose mass replies, "
                "and remember a human decides before any reply is sent."
            ),
            "criteria": {label: HANDLING_DESCRIPTIONS[label] for label in HANDLING},
        },
    }


def build_rank_questions(candidates: list[Candidate]) -> dict:
    """All ranking heads for one slate; sent together in a single request."""

    offered = {candidate.id: candidate.text for candidate in candidates}
    questions: dict = {
        "best_reply": {
            "type": "choice",
            "instructions": (
                "Which single candidate is the best respectful counterspeech reply? "
                "Prefer de-escalation and humanization; never target an individual."
            ),
            "criteria": dict(offered),
        }
    }
    for dimension in DIMENSIONS:
        questions[dimension] = {
            "type": "choice",
            "instructions": (
                f"Which candidate best satisfies this dimension: {DIMENSION_DESCRIPTIONS[dimension]}"
            ),
            "criteria": dict(offered),
        }
    quality_legend = "; ".join(f"{label}" for label in QUALITY_CRITERIA)
    for candidate in candidates:
        questions[f"quality_{candidate.id}"] = {
            "type": "score",
            "instructions": (
                f"Rate the overall quality of candidate {candidate.id} ({candidate.text!r}) "
                f"from worst to best over the ordered criteria ({quality_legend})."
            ),
            "criteria": list(QUALITY_CRITERIA),
        }
    return questions


def _parse_triage(answers: dict, post_id: str) -> Triage:
    expected = set(TRIAGE_QUESTIONS)
    _answers_object(answers, expected, "triage")
    hateful = _noul(answers, "hateful")
    targets = _noul(answers, "targets_protected_group")
    slur = _noul(answers, "has_slur")
    severity_dist = _score(answers, "severity", SEVERITY_CRITERIA)
    severity = sum((index + 1) * severity_dist[str(index)] for index in range(len(SEVERITY_CRITERIA)))
    category, category_probs, _ = _choice(answers, "category", CATEGORIES)
    handling, handling_probs, handling_confidence = _choice(answers, "handling", HANDLING)
    return Triage(
        post_id=post_id,
        hateful=hateful,
        targets_protected_group=targets,
        has_slur=slur,
        severity_dist=severity_dist,
        severity=severity,
        category=category,
        category_probs=category_probs,
        handling=handling,
        handling_probs=handling_probs,
        confidence=handling_confidence,
        answers=dict(answers),
    )


def _parse_ranking(answers: dict, post_id: str, candidates: list[Candidate]) -> Ranking:
    ids = [candidate.id for candidate in candidates]
    expected = {"best_reply", *DIMENSIONS} | {f"quality_{candidate.id}" for candidate in candidates}
    _answers_object(answers, expected, "ranking")
    best, best_probs, confidence = _choice(answers, "best_reply", tuple(ids))
    dimensions: dict[str, dict[str, float]] = {}
    for dimension in DIMENSIONS:
        _, probabilities, _ = _choice(answers, dimension, tuple(ids))
        dimensions[dimension] = probabilities
    quality: dict[str, float] = {}
    quality_dists: dict[str, dict[str, float]] = {}
    span = len(QUALITY_CRITERIA) - 1
    for candidate in candidates:
        distribution = _score(answers, f"quality_{candidate.id}", QUALITY_CRITERIA)
        quality_dists[candidate.id] = distribution
        quality[candidate.id] = sum(index * distribution[str(index)] for index in range(len(QUALITY_CRITERIA))) / span
    return Ranking(
        post_id=post_id,
        quality=quality,
        quality_dists=quality_dists,
        dimensions=dimensions,
        best=best,
        best_probs=best_probs,
        confidence=confidence,
    )


class LiveJudge:
    """Live TypeSafe judge. Each method issues exactly one fan-out request.

    Construction is cheap and side-effect free: the API key is resolved lazily on
    the first call and never stored on the instance.
    """

    def __init__(self, model: str | None = None, attempts: int = 3) -> None:
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.attempts = attempts

    def _send(self, body: dict, parse: Callable[[dict], T]) -> tuple[T, dict, dict]:
        """POST one body and return ``(parsed, meta, raw_answers)``.

        Validation failures and retryable HTTP statuses are retried with
        exponential backoff; after ``attempts`` the call raises :class:`JevError`.
        """

        key = ensure_api_key()
        last_error: Exception | None = None
        started = time.perf_counter()
        for attempt in range(self.attempts):
            try:
                response = CLIENT.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as error:
                last_error = error
                if attempt < self.attempts - 1:
                    time.sleep(0.4 * 2**attempt)
                continue
            if response.status_code in RETRYABLE and attempt < self.attempts - 1:
                time.sleep(0.5 * 2**attempt)
                continue
            if response.is_error:
                raise JevError(f"TypeSafe returned HTTP {response.status_code}")
            try:
                payload = response.json()
                answers = payload["answers"]
                parsed = parse(answers)
            except (KeyError, TypeError, ValueError, JevError) as error:
                last_error = error
                if attempt < self.attempts - 1:
                    time.sleep(0.3 * 2**attempt)
                continue
            meta = {
                "model": str(payload.get("model", self.model)),
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "usage": dict(payload.get("usage", {})),
                "request": body,
            }
            return parsed, meta, dict(answers)
        raise JevError(f"no usable Jev answer after {self.attempts} attempts: {last_error}")

    def triage(self, example: Example) -> Triage:
        """Classify one post with every triage head in a single request."""

        body = {
            "model": self.model,
            "state": {
                "task": TRIAGE_TASK,
                "post": example.post(),
                "safety": list(SAFETY_RULES),
            },
            "questions": build_triage_questions(),
        }
        triage, meta, _ = self._send(body, lambda answers: _parse_triage(answers, example.id))
        triage.meta = meta
        return triage

    def rank(self, example: Example, candidates: list[Candidate]) -> Ranking:
        """Rank 2..8 candidate replies with every head in a single request."""

        if not 2 <= len(candidates) <= 8:
            raise JevError("rank requires between 2 and 8 candidates")
        if len({candidate.id for candidate in candidates}) != len(candidates):
            raise JevError("candidate ids must be unique")
        body = {
            "model": self.model,
            "state": {
                "task": RANK_TASK,
                "post": example.post(),
                "safety": list(SAFETY_RULES),
            },
            "questions": build_rank_questions(candidates),
        }
        ranking, meta, raw_answers = self._send(
            body, lambda answers: _parse_ranking(answers, example.id, candidates)
        )
        ranking.meta = {**meta, "raw_answers": raw_answers}
        return ranking
