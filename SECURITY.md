# Security

This is a local, human-in-the-loop demo. It ships no credentials, makes no paid API call in
CI, and has no posting path. The properties below are the security guarantees the design
intends; when in doubt, trust the code, not this file.

## No secrets in the repo

- `.env` is gitignored and `.env.example` holds empty placeholders only.
- CI and the demo workflow run the `--offline` path, which never reads a key.
- No workflow references `TYPESAFE_API_KEY` or `TEXT_MODEL_API_KEY`.
- If you believe a real key was committed, treat it as compromised, rotate it, and open a
  private advisory (see below).

## Key handling

Live mode resolves `TYPESAFE_API_KEY` in this order:

1. the process environment (`TYPESAFE_API_KEY`),
2. `<repo>/.env`,
3. `~/jev-ultrafast/.env`.

Text-model drafting (`--drafts llm`) resolves `TEXT_MODEL_API_KEY` from the environment and
then `<repo>/.env` only. A missing key is a clean error, not a fallback to an unauthenticated
call.

The key is placed only in the `Authorization` header of the request that needs it. It is
never printed, logged, written to disk, or stored on the judge instance; resolution happens at
call time, and CI never triggers it.

## The `--offline` path never reads keys

`--offline` is the default and is what CI exercises. It selects the local deterministic stub,
which never opens a socket and never calls `ensure_api_key`/`resolve_text_api_key`. `--live`
and `--drafts llm` are explicit opt-ins and are the only paths that read a key.

## No-network guarantee

There is no posting, no X/Twitter API, no browser automation, and no outbound request of any
kind on the send path.

- The review server binds a **loopback address only** (`127.0.0.1`, `localhost`, or `::1`);
  `serve()` raises rather than bind a non-loopback host, and each request is rejected with
  `403` if its `Host` header is not local.
- `POST /api/outbox` is the only write path in the project. It validates the payload and
  appends exactly one JSON line to `<results_dir>/outbox.jsonl`; the record carries
  `"network": "none"`.
- Request bodies are size-bounded (`32 KiB`), text is length-bounded (`2000` chars), the
  `approved` flag must be `true`, and the `post_id` must match one the run actually produced.
- `tests/test_egress.py` statically enforces that the review server and its static UI contain
  no outbound-request capability (no `urllib.request`, `http.client`, `requests`, `urlopen`,
  `HTTPConnection`, or `socket`, and no `httpx` import), and that the outbox is the only write
  path.

The live training path (`--live`, `systemone`) and the optional text-model path (`--drafts
llm`) are the only components that make outbound requests; both are opt-in and neither is on
the send path.

## Model output is validated

The live judge does not trust the model. For each fan-out answer it requires the exact offered
keyset, finite probabilities in `[0, 1]`, and distributions that sum to `1` (within `0.02`).
Validation failures and retryable HTTP statuses (`429`, `503`, `529`) are retried with
exponential backoff; after the attempt budget the call raises rather than acting on a
malformed answer. LLM-drafted candidates are validated before they leave `drafts.py`: non-empty
strategy and text, unique strategies, a length cap, and rejection of URLs, `@handles`, and the
`[SLUR]` placeholder.

## Fail-closed gate

The gate is the only component allowed to turn a probabilistic triage into an action, and it
fails closed. High-stakes categories, individual-targeted hate, `severity >= 4`, and low
confidence all route to `human_review`; the pipeline calls drafting and ranking **only** for a
`draft` decision. A triage failure produces a neutral placeholder triage with a
`human_review` gate so the item still reaches a person instead of being silently dropped.

## Data minimization

- The shipped corpus is **synthetic** and CC0-1.0: no real slur text, no real people, no real
  named groups, and no author, URL, or platform-metadata fields.
- Posts carry opaque synthetic ids (for example `synthetic-0000`). The live model receives only
  `{"id", "text"}`; ground-truth labels are used solely by the offline stub, the calibration
  report, and tests.
- The local outbox stores the reviewer-approved text, the post/candidate ids, a timestamp, and
  `"network": "none"` — nothing more. It is gitignored by default.

## Reporting a vulnerability

Please open a **private security advisory** on the repository rather than a public issue. Do
not include real keys, real toxic content, or personal data in the report; a synthetic
reproduction is enough.
