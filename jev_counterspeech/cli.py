"""Command line: run the triage -> gate -> draft -> rank pipeline and write results.

Offline is the default and uses the calibrated stub; ``--live`` talks to the real Jev
API and needs a ``TYPESAFE_API_KEY``. The gate refuses to draft anything it considers
unsafe, so drafting and ranking only ever run for posts that passed triage. A human
still reviews every drafted reply; nothing is posted to a network.

With ``--serve`` the local (loopback) human-review UI is started after the results are
written. The server import is deferred so the CLI works without the UI dependencies.
"""

from __future__ import annotations

import argparse
import sys

from . import pipeline, report
from .jev import JevError
from .schemas import DEFAULT_GATE_THRESHOLD

#: Number of equal-width bins used for the reliability table.
_BINS = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jev-counterspeech",
        description="Triage, gate, draft, and rank counterspeech candidates; a human decides.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="use the local stub (default)")
    mode.add_argument("--live", action="store_true", help="call the real Jev API (needs TYPESAFE_API_KEY)")
    parser.add_argument(
        "--stub",
        choices=("calibrated", "overconfident", "oracle"),
        default="calibrated",
        help="offline stub behaviour (default: calibrated)",
    )
    parser.add_argument("--seed", type=int, default=7, help="seed for the examples and stub (default: 7)")
    parser.add_argument("--limit", type=int, default=24, help="maximum number of posts to process (default: 24)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_GATE_THRESHOLD,
        help=f"confidence at or above which Jev's handling answer is trusted (default: {DEFAULT_GATE_THRESHOLD})",
    )
    parser.add_argument(
        "--drafts",
        choices=("template", "llm"),
        default="template",
        help="candidate-drafting mode (default: template)",
    )
    parser.add_argument("--include-public", action="store_true", help="include the public examples in the dataset")
    parser.add_argument("--results-dir", default="results", help="where to write report artifacts (default: results)")
    parser.add_argument("--serve", action="store_true", help="start the local human-review UI after writing results")
    parser.add_argument("--port", type=int, default=8781, help="port for the review UI (default: 8781)")
    parser.add_argument("--quiet", action="store_true", help="only print the written paths")
    return parser


def _calibration(examples, items) -> dict:
    """Triage confidence calibration: Brier/ECE of ``triage.hateful`` vs the labels.

    Only posts that produced a real triage are scored, so fail-closed placeholders do
    not distort the headline. ``baseline_brier`` is the always-0.5 guess.
    """

    labels = {example.id: float(example.label_hateful) for example in examples}
    pairs: list[tuple[float, float]] = []
    for item in items:
        if item.triage.meta.get("failed"):
            continue
        if item.post_id in labels:
            pairs.append((float(item.triage.hateful), labels[item.post_id]))

    bins = [{"sum_pred": 0.0, "sum_true": 0.0, "count": 0} for _ in range(_BINS)]
    for predicted, truth in pairs:
        index = min(_BINS - 1, max(0, int(predicted * _BINS)))
        bins[index]["sum_pred"] += predicted
        bins[index]["sum_true"] += truth
        bins[index]["count"] += 1

    count = len(pairs)
    reliability: list[dict] = []
    ece = 0.0
    for index, bucket in enumerate(bins):
        lower = index / _BINS
        upper = (index + 1) / _BINS
        row_count = bucket["count"]
        if row_count:
            mean_predicted = bucket["sum_pred"] / row_count
            empirical_rate = bucket["sum_true"] / row_count
            ece += (row_count / count) * abs(mean_predicted - empirical_rate)
        else:
            mean_predicted = 0.0
            empirical_rate = 0.0
        reliability.append(
            {
                "lower": lower,
                "upper": upper,
                "mean_predicted": mean_predicted,
                "empirical_rate": empirical_rate,
                "count": row_count,
            }
        )

    if not count:
        return {
            "count": 0,
            "brier": 0.0,
            "baseline_brier": 0.0,
            "ece": 0.0,
            "reliability": reliability,
        }

    brier = sum((predicted - truth) ** 2 for predicted, truth in pairs) / count
    baseline_brier = sum((0.5 - truth) ** 2 for _, truth in pairs) / count
    return {
        "count": count,
        "brier": brier,
        "baseline_brier": baseline_brier,
        "ece": ece,
        "reliability": reliability,
    }


def _print_summary(result: pipeline.RunResult, paths: dict[str, str]) -> None:
    meta = result.meta
    counts = meta["counts"]
    mode_line = f"mode={meta['mode']}"
    if meta["stub"]:
        mode_line += f" (stub={meta['stub']})"

    print(
        f"JEV-COUNTERSPEECH  {mode_line}  examples={meta['examples']}  seed={meta['seed']}  "
        f"threshold={meta['threshold']:.2f}  drafts={meta['draft_mode']}"
    )
    print(
        f"  gate: draft={counts['draft']} human_review={counts['human_review']} "
        f"ignore={counts['ignore']} report={counts['report']} refused={counts['refused']}"
    )

    calibration = _calibration(result.examples, result.items)
    print(
        f"  triage calibration: n={calibration['count']} Brier={calibration['brier']:.4f} "
        f"ECE={calibration['ece']:.4f} (baseline Brier {calibration['baseline_brier']:.4f})"
    )
    print("  reliability:")
    print("    bin        mean-pred  empirical  count")
    for row in calibration["reliability"]:
        if row["count"] == 0:
            continue
        print(
            f"    [{row['lower']:.1f},{row['upper']:.1f})  {row['mean_predicted']:.3f}      "
            f"{row['empirical_rate']:.3f}     {row['count']}"
        )


def _start_server(results_dir: str, port: int) -> int:
    try:
        from . import server
    except Exception as error:  # pragma: no cover - depends on optional UI wiring
        print(f"jev-counterspeech: review UI unavailable: {error}", file=sys.stderr)
        return 1
    try:
        server.serve(results_dir, port=port)
    except Exception as error:  # pragma: no cover - depends on optional UI wiring
        print(f"jev-counterspeech: review UI failed to start: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1:
        print("error: --limit must be at least 1", file=sys.stderr)
        return 2

    try:
        result = pipeline.run(
            offline=not args.live,
            stub=args.stub,
            seed=args.seed,
            limit=args.limit,
            threshold=args.threshold,
            draft_mode=args.drafts,
            include_public=args.include_public,
        )
    except JevError as error:
        print(f"jev-counterspeech: {error}", file=sys.stderr)
        return 1

    paths = report.write_results(result.examples, result.items, result.meta, args.results_dir)

    if args.quiet:
        for path in paths.values():
            print(path)
    else:
        _print_summary(result, paths)
        print(f"  wrote {', '.join(paths.values())}")

    if args.serve:
        return _start_server(args.results_dir, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
