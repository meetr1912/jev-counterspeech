"""Candidate reply drafting: the only component allowed to generate free text.

Two modes:

* ``template`` (default, offline, deterministic) fills safe, pre-written
  counterspeech scaffolds. It makes no network call and never reads the post
  text, so it can never echo a slur or a hateful claim.
* ``llm`` asks an OpenAI-compatible chat endpoint (``TEXT_MODEL_API_KEY``,
  ``TEXT_MODEL_BASE_URL``, ``TEXT_MODEL``) for JSON candidates. Every returned
  candidate is validated before it leaves this module; any failure raises
  ``RuntimeError`` rather than returning unvalidated text.

The key is resolved from the process environment and then ``<repo>/.env`` and is
never printed, logged, or written to disk.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx

from .schemas import Candidate, Example, Triage

DRAFT_MODES = ("template", "llm")

#: Short, reusable safety rules. They are injected into the LLM system prompt and
#: describe what every emitted reply must (and must not) contain.
SAFETY_RULES: tuple[str, ...] = (
    "Acknowledge the person; challenge the claim, never the individual.",
    "Never repeat, quote, or paraphrase the slur or the hateful claim.",
    "Humanize the targeted group; do not dehumanize or 'other' anyone.",
    "Assert a shared norm instead of shaming or scoring points.",
    "Invite reflection or dialogue; stay calm, respectful, and non-sarcastic.",
    "Never name or target an individual, and never instruct mass replies.",
    "No URLs, no handles, no emoji; keep every reply under 280 characters.",
)

#: Strategies the template drafter cycles through.
TEMPLATE_STRATEGIES: tuple[str, ...] = (
    "empathy_question",
    "shared_norm",
    "correct_record",
    "invite_dialogue",
)

#: Strategies accepted from the LLM. ``myth_bust`` is allowed but ranked lower on
#: backfire safety.
ALLOWED_STRATEGIES: tuple[str, ...] = TEMPLATE_STRATEGIES + ("myth_bust",)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
MAX_LLM_TEXT_CHARS = 600
DEFAULT_TIMEOUT = 60.0

_REPO_ROOT = Path(__file__).resolve().parent.parent
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_HANDLE_RE = re.compile(r"@\w")

_TEMPLATES: dict[str, str] = {
    "empathy_question": (
        "That framing paints a whole community with one brush. I know the claim "
        "doesn't match what I've seen. What's behind it? I'd genuinely like to understand."
    ),
    "shared_norm": (
        "We can disagree about plenty, but no one here has to lose their dignity for "
        "that. Treating people as people is something we can all count on, even when we argue."
    ),
    "correct_record": (
        "Broad claims about any group rarely survive a look at the evidence. It's worth "
        "checking what the facts actually say before passing a sweeping judgment along."
    ),
    "invite_dialogue": (
        "I'd rather understand than pile on. If you've had a different experience, I'm "
        "open to hearing it. What led you to this post?"
    ),
}

SYSTEM_PROMPT = "\n".join(
    [
        "You write short, safe counterspeech replies for a human moderator to review.",
        "Hard rules (never violate):",
        *[f"- {rule}" for rule in SAFETY_RULES],
        "",
        "Return ONLY a JSON object of the form:",
        '{"candidates": [{"strategy": "<strategy>", "text": "<reply>"}]}',
        "Use distinct strategies chosen from: " + ", ".join(ALLOWED_STRATEGIES) + ".",
        "Write plain, respectful prose. Do not include markdown fences or commentary.",
    ]
)


def load_env_file(path: Path) -> None:
    """Load ``KEY=VALUE`` lines into ``os.environ`` without overwriting existing keys."""

    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def resolve_text_api_key() -> str | None:
    """Resolve ``TEXT_MODEL_API_KEY`` from the environment or ``<repo>/.env`` only."""

    if not os.environ.get("TEXT_MODEL_API_KEY"):
        load_env_file(_REPO_ROOT / ".env")
    return os.environ.get("TEXT_MODEL_API_KEY") or None


def text_llm_available() -> bool:
    """True iff a text-model key is resolvable. Never makes a network call."""

    return resolve_text_api_key() is not None


def draft_candidates(
    example: Example,
    triage: Triage,
    mode: str = "template",
    limit: int = 4,
) -> list[Candidate]:
    """Draft up to ``limit`` candidate replies for ``example`` in the chosen mode."""

    if mode not in DRAFT_MODES:
        raise ValueError(f"unknown draft mode {mode!r}; choose from {DRAFT_MODES}")
    if limit <= 0:
        return []
    if mode == "template":
        return _draft_template(limit)
    return draft_with_llm(example, triage, limit=limit)


def _draft_template(limit: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    for strategy in TEMPLATE_STRATEGIES:
        if len(candidates) >= limit:
            break
        candidates.append(
            Candidate(
                id=f"c{len(candidates) + 1}",
                text=_TEMPLATES[strategy],
                strategy=strategy,
                origin="template",
            )
        )
    return candidates


def draft_with_llm(example: Example, triage: Triage, limit: int = 4) -> list[Candidate]:
    """Draft candidates with an OpenAI-compatible chat endpoint.

    Raises ``RuntimeError`` when no key is configured, the request fails, or the
    model returns anything that does not pass validation. The key is never logged.
    """

    if limit <= 0:
        return []
    key = resolve_text_api_key()
    if not key:
        raise RuntimeError(
            "TEXT_MODEL_API_KEY is not set; add it to the environment or <repo>/.env "
            "to use mode='llm'"
        )
    base_url = os.environ.get("TEXT_MODEL_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("TEXT_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(example, triage, limit)},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"text model request failed: {type(exc).__name__}: {exc}") from exc
    return _parse_candidates(content, limit)


def _user_prompt(example: Example, triage: Triage, limit: int) -> str:
    return (
        f"Post id: {example.id}\n"
        "Post text (it may contain a placeholder such as [SLUR]; never repeat it):\n"
        f"{example.text}\n\n"
        f"Triage: category={triage.category}, severity={triage.severity:.2f}, "
        f"handling={triage.handling}.\n"
        f"Write {min(limit, len(ALLOWED_STRATEGIES))} distinct replies and return the JSON object."
    )


def _parse_candidates(content: str, limit: int) -> list[Candidate]:
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("text model did not return valid JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("candidates"), list):
        raise RuntimeError("text model JSON is missing a 'candidates' list")

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for index, raw in enumerate(parsed["candidates"]):
        if len(candidates) >= limit:
            break
        candidates.append(_validate_candidate(raw, index, seen))
    if not candidates:
        raise RuntimeError("text model returned no usable candidates")
    return candidates


def _validate_candidate(raw: object, index: int, seen: set[str]) -> Candidate:
    if not isinstance(raw, dict):
        raise RuntimeError(f"candidate {index} is not a JSON object")
    strategy = str(raw.get("strategy", "")).strip()
    text = str(raw.get("text", "")).strip()
    if not strategy:
        raise RuntimeError(f"candidate {index} has an empty strategy")
    if strategy in seen:
        raise RuntimeError(f"candidate {index} repeats strategy {strategy!r}")
    if not text:
        raise RuntimeError(f"candidate {index} has empty text")
    if len(text) > MAX_LLM_TEXT_CHARS:
        raise RuntimeError(f"candidate {index} exceeds {MAX_LLM_TEXT_CHARS} characters")
    if "[slur]" in text.lower():
        raise RuntimeError(f"candidate {index} echoes the [SLUR] placeholder")
    if _URL_RE.search(text):
        raise RuntimeError(f"candidate {index} contains a URL")
    if _HANDLE_RE.search(text):
        raise RuntimeError(f"candidate {index} contains an @handle")
    seen.add(strategy)
    return Candidate(id=f"c{index + 1}", text=text, strategy=strategy, origin="llm")
