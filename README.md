# Jev Counterspeech

**A responsible counterspeech assistant: Jev (TypeSafe) triages and ranks, a text model only drafts, and a human stays in the loop. Nothing is ever posted.**

Jev reads a post and answers typed `noul` / `score` / `choice` questions about it — one
fan-out request, native probabilities, no prose to parse. A small, ordered gate turns that
read into an explicit action; only a `draft` decision unlocks candidate replies. Jev then
ranks the candidates on de-escalation, humanization, factual grounding, and backfire safety.
A person reviews every draft and "sends" it to a **local file**. There is no posting path.

> This is a local, human-in-the-loop demo and evaluation harness. It is not a moderation
> product, not a bot, and not connected to any platform. The only write the UI can make is
> a JSON line in `results/outbox.jsonl` on your machine.

## What it is / what it is NOT

It **is** a demonstration that a capable model can be kept on the safe side of a hard line:
triage and ranking are probabilistic, drafting is separable and optional, and the gate — not
the model — decides what may be drafted. It is also a calibration harness: the headline metric
is how honest Jev's stated uncertainty is, measured on labeled data, never engagement.

It is **not**, and deliberately ships with none of the machinery for:

- **posting** anything to any network;
- any **X/Twitter API** (or any other platform API);
- **browser automation** or UI driving;
- **platform integration** of any kind;
- **mass replies**, coordinated replies, or astroturfing;
- **targeting individuals** (the gate refuses to draft when a post targets a person);
- **surveillance**, monitoring, watchlists, or profiling of people or groups.

## Pipeline

Six stages, in order. The safety invariant is that stages 3–4 run **only** for a `draft` gate.

1. **Triage — one fan-out request.** `LiveJudge.triage` sends a single
   `POST https://api.typesafe.ai/v1/systemone` request per post with six typed heads:
   three `noul` probabilities (`hateful`, `targets_protected_group`, `has_slur`), one
   ordered `score` over severity 1–5, one `choice` over the six content categories, and one
   `choice` over handling (`ignore`, `report`, `reply`, `human_review`). The request carries
   only the post text and an opaque id — never the labels.
2. **Gate — explicit and fail-closed.** `gate.decide_gate` evaluates nine ordered rules; the
   first match wins. Anything uncertain or high-stakes becomes `human_review`, and only a
   confident, group-targeted, reply-worthy post becomes `draft`.
3. **Draft — only for `draft`-gated items.** `drafts.draft_candidates` runs in `template`
   mode by default (deterministic, offline, never reads the post text) or `llm` mode
   (`--drafts llm`) against an OpenAI-compatible chat endpoint. The text model only drafts;
   Jev never authors reply text.
4. **Rank — Jev scores the slate.** A second single fan-out request asks Jev to pick the best
   candidate and score each one on the four ranking dimensions:
   `de_escalation`, `humanization`, `factual_grounding`, `backfire_safety`, plus per-candidate
   overall quality. Jev selects among precomputed options; it does not write.
5. **Human review — local UI.** `--serve` starts a loopback-only inspector at
   `http://127.0.0.1:8781`. It shows the triage, the gate reasons, the candidates and Jev's
   ranking. The editable draft is prefilled with Jev's best candidate; if the gate did not
   draft, the UI offers no reply at all. **"Send to local outbox"** appends one JSON line to
   `results/outbox.jsonl`. Nothing leaves the machine.
6. **Calibration report.** `report.write_results` writes `results/report.json`,
   `results/REPORT.md`, and a reliability diagram (`results/reliability.svg`) with its ASCII
   twin (`results/reliability.txt`). The headline is Brier / ECE / log loss against the
   always-0.5 baseline, with a reliability table — a calibration measurement, not an
   engagement metric.

### The gate, in order

Rules are evaluated top to bottom; the first match wins.

| # | Condition | Action | Reason recorded |
| --- | --- | --- | --- |
| 1 | `category == threat` | `human_review` | category=threat is high-stakes |
| 2 | `hateful >= 0.5` and targeted at an individual, not a protected group | `human_review` | targets an individual, not a protected group |
| 3 | `severity >= 4` | `human_review` | severity >= 4 (slur/dehumanization) is high-stakes |
| 4 | `confidence < threshold` (default `0.65`) | `human_review` | confidence ... < threshold ... |
| 5 | `handling == ignore` | `ignore` | handling=ignore |
| 6 | `handling == report` | `report` | handling=report |
| 7 | `handling == human_review` | `human_review` | handling=human_review |
| 8 | `handling == reply` but `hateful < 0.5` | `human_review` | handling=reply but hateful probability below 0.5 |
| 9 | otherwise | `draft` | confident, group-targeted, reply-worthy |

`severity >= 4` (a slur or dehumanizing language) is deliberately treated as high-stakes and
is **never** auto-drafted, even when Jev is confident. That is a conscious
safety-over-capability choice: the pipeline will only *propose* text for milder,
group-directed stereotype/othering content, and a person still has to approve it.

## Files

| File | Job |
| --- | --- |
| `jev_counterspeech/schemas.py` | Frozen vocabulary and types: categories, handling, severity, four ranking dimensions, the `0.65` default gate threshold |
| `jev_counterspeech/jev.py` | Live TypeSafe System One client: one fan-out `systemone` request for triage, one for ranking; validates every answer |
| `jev_counterspeech/gate.py` | The ordered, side-effect-free, fail-closed confidence/safety gate |
| `jev_counterspeech/stub.py` | Deterministic, no-network offline judge: `calibrated`, `overconfident`, `oracle` |
| `jev_counterspeech/drafts.py` | Candidate reply drafting: `template` (default, offline) or optional `llm`; validates every emitted candidate |
| `jev_counterspeech/pipeline.py` | Orchestration `triage -> gate -> (if draftable) draft -> rank`; per-post failure containment |
| `jev_counterspeech/report.py` | Builds the calibration report and writes `results/report.json`, `REPORT.md`, `reliability.svg`, `reliability.txt` |
| `jev_counterspeech/metrics.py` | Brier, log loss, ECE, reliability table, multiclass Brier / cross-entropy, ASCII + SVG renderers (pure stdlib) |
| `jev_counterspeech/data.py` | Deterministic synthetic corpus and the empty `PUBLIC_SAMPLES` opt-in extension point |
| `jev_counterspeech/cli.py` | Argument parsing, summary printing, and entry point |
| `jev_counterspeech/server.py` | Loopback-only review UI; the single write path appends to the local outbox |
| `jev_counterspeech/static/` | The review UI (`index.html`, `app.js`, `style.css`) |
| `data/README.md` | Data provenance, licensing, and responsible-use notes |
| `.github/workflows/ci.yml` | Lint, tests, and package build on Python 3.11 and 3.12 |
| `.github/workflows/demo.yml` | Offline demo run; uploads `results/` as an artifact |

## Quickstart

```bash
cd ~/jev-counterspeech
uv sync --dev

# Offline (default): no key, no network, deterministic calibrated stub.
uv run jev-counterspeech --offline --limit 24 --seed 7 --results-dir results

# Then open the local-only human-review UI at http://127.0.0.1:8781
uv run jev-counterspeech --offline --limit 24 --seed 7 --results-dir results --serve

# Live Jev (real API; needs TYPESAFE_API_KEY):
uv run jev-counterspeech --live --limit 24 --seed 7 --results-dir results

# LLM-drafted candidates (needs TEXT_MODEL_API_KEY; template is the default):
uv run jev-counterspeech --offline --drafts llm --limit 24 --seed 7 --results-dir results

# Calibration "teeth": an overconfident stub must score a higher ECE than calibrated.
uv run jev-counterspeech --offline --stub overconfident --limit 120 --seed 7 --results-dir results
uv run jev-counterspeech --offline --stub oracle --limit 120 --seed 7 --results-dir results

# Move the confidence gate (0.0-1.0; default 0.65):
uv run jev-counterspeech --offline --threshold 0.8 --limit 24 --seed 7 --results-dir results
```

Useful flags: `--stub calibrated|overconfident|oracle`, `--drafts template|llm`,
`--threshold`, `--include-public`, `--port` (review UI, default `8781`), `--quiet`.

The TypeSafe key is read from `TYPESAFE_API_KEY`, then `<repo>/.env`, then
`~/jev-ultrafast/.env`. The text-model key is read from `TEXT_MODEL_API_KEY`, then
`<repo>/.env`. Keys are never printed, logged, or written.

## Offline mode

`--offline` is the default. It never touches the network and never reads a key, and it is
deterministic for a given `(mode, seed)`.

- **`calibrated`** (default) emits each example's true generative probabilities
  (`hateful = example.p_hateful`, and so on). Confidence is monotone in decisiveness: a
  borderline post reports low confidence; a decisive one reports high confidence.
- **`overconfident`** keeps the calibrated ranking but sharpens every probability toward 0/1
  and adds a positive over-prediction bias. It is the calibration **"teeth"** stub: it must
  score a higher ECE than `calibrated`, which is exactly what the teeth test asserts.
- **`oracle`** returns exact one-hot / 0–1 answers matching the labels and therefore scores a
  Brier of **0**. It is the anchor that proves the scoring pipeline is wired correctly.

## Data

Everything shipped in this repository is **synthetic**, written for this project, and released
under **CC0-1.0**. There are no real slurs and no real named people or groups; slurs appear only
as the placeholder `[SLUR]`, and groups are invented (for example "the Northland community" and
"Group A"). The corpus is deterministic from `(seed, n)` and spans all six categories plus an
individual-targeted class the gate must refuse. `PUBLIC_SAMPLES` is an empty tuple and is the
opt-in extension point for a user-supplied, locally licensed sample.

Two well-known corpora are intentionally **not** bundled: **CONAN** is research-use and does not
permit redistribution, and **HateXplain**'s license conflicts with shipping its text here. See
[`data/README.md`](data/README.md) for provenance, opt-in instructions, and responsible-use
notes.

## How it was verified

```bash
uv sync --dev
uv run ruff check .
uv run pytest -q
uv build
uv run jev-counterspeech --offline --limit 120 --seed 7 --results-dir results
```

Observed on this checkout (Linux, Python 3.12, `uv 0.12`):

```text
$ uv run ruff check .
All checks passed!

$ uv run pytest -q
54 passed, 1 deselected in 2.34s

$ uv run pytest -q -m live
1 skipped, 54 deselected in 0.07s        # no key, no network; live test is opt-in

$ uv build
Successfully built dist/jev_counterspeech-0.1.0.tar.gz
Successfully built dist/jev_counterspeech-0.1.0-py3-none-any.whl

$ uv run jev-counterspeech --offline --limit 120 --seed 7 --results-dir results
JEV-COUNTERSPEECH  mode=offline (stub=calibrated)  examples=120  seed=7  threshold=0.65  drafts=template
  gate: draft=28 human_review=65 ignore=19 report=8 refused=92
  triage calibration: n=120 Brier=0.0909 ECE=0.0748 (baseline Brier 0.2500)
  wrote results/report.json, results/REPORT.md, results/reliability.svg, results/reliability.txt
```

Calibration "teeth": the `overconfident` stub scores **Brier 0.1174 / ECE 0.1727** at the
same seed — a strictly higher ECE than `calibrated` (0.0748) — while `oracle` scores
**Brier 0.0000 / ECE 0.0000**. That is what makes the metric meaningful rather than decorative.

The fail-closed behaviour is pinned by the gate-refusal test
`tests/test_gate.py::test_gate_refuses_to_draft_for_low_confidence_and_high_stakes`: a
confident threat-category, individual-targeted, or `severity >= 4` post still returns
`human_review`. `tests/test_pipeline.py::test_pipeline_never_drafts_or_ranks_when_gate_refuses`
additionally asserts the pipeline never calls drafting or ranking for any refused class
(`threat_category`, `targets_individual`, `severity_4`, `severity_5`, `low_confidence`,
`handling_human_review`, `reply_but_not_hateful`), and only does so for a clean case.
`tests/test_egress.py` asserts the review server and its static UI contain no outbound-request
capability, that the outbox handler performs no socket I/O, and that the server refuses to
bind a non-loopback host.

## Safety rails / responsible use

Guarantees, each enforced in code:

- **Human approval per item.** Every draft is a proposal; the UI requires an explicit
  **approved** flag before it writes anything, and there is no other write path.
- **No network egress from the send path.** The review server binds loopback only, and its
  single write appends a JSON line to `results/outbox.jsonl`.
- **No secrets.** `.env` is gitignored and `.env.example` holds empty placeholders. The
  `--offline` path used by CI never reads a key.
- **Validated model output.** Every Jev answer's keyset must match the offered criteria, all
  probabilities must be finite and in `[0, 1]`, and distributions must sum to `1`; otherwise the
  request is retried and then fails. LLM-drafted candidates are rejected if they are malformed,
  too long, repeat a strategy, echo `[SLUR]`, or contain a URL or `@handle`.
- **Fail-closed gate.** Low confidence and high stakes route to a human. A triage failure keeps
  the post with a neutral placeholder and a `human_review` gate rather than dropping it.
- **Slur masking.** Shipped text uses the `[SLUR]` placeholder, and the template drafter never
  reads the post text, so it can never echo a slur.
- **The metric is calibration, not engagement.** Brier / ECE are reported against the always-0.5
  baseline so miscalibration is visible. They must not be optimized as a popularity signal.

**Out of scope / prohibited uses.** This project must not be used for automated or bulk
posting; astroturfing or coordinated inauthentic behavior; harassment or pile-ons; doxxing or
targeting individuals; scraping or surveillance; election or campaign operations; or government
surveillance. If your use needs a posting integration, this is the wrong tool.

## CI / no secrets

`.github/workflows/ci.yml` runs lint, tests, and a package build on Python 3.11 and 3.12.
`.github/workflows/demo.yml` runs the offline demo and uploads `results/` as an artifact. Both
run **without any secrets**: the offline path never reads `TYPESAFE_API_KEY` or
`TEXT_MODEL_API_KEY`, and no workflow references them.

## License

MIT © 2026 meetr1912 — see [`LICENSE`](LICENSE). The synthetic data ships under CC0-1.0 —
see [`data/LICENSE`](data/LICENSE).

MIT cannot prevent a fork from repurposing this code. The no-posting guarantee is therefore
enforced in the implementation rather than by the license: the server refuses to bind a
non-loopback host, there is no outbound request on the send path, and the only record of a
"send" is a local JSONL file. Forks that add a posting integration are on their own; this
repository does not contain one.

See [`SECURITY.md`](SECURITY.md) for key handling, the no-network guarantee, and private
disclosure.
