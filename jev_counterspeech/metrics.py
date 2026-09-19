"""Calibration metrics — pure stdlib, hand-verifiable, no numpy.

Definitions (all means are over the supplied events), mirroring ``jev-arena``:

* **Brier** ``= mean((p - y)^2)`` for binary events.
* **Log loss** ``= -mean(y*log(p) + (1-y)*log(1-p))`` with ``p`` clipped to
  ``[eps, 1-eps]`` (``eps=1e-12``) so a confident miss is finite but severe.
* **ECE** (expected calibration error) over equal-width bins:
  ``sum_b (n_b/N) * |mean_pred_b - empirical_rate_b|``. The last bin is
  inclusive of ``1.0``.
* **Reliability table** — per-bin predicted mean, empirical rate, count.
* **Multiclass Brier** ``= mean_i sum_c (p_ic - y_ic)^2``.
* **Cross-entropy** ``= -mean_i sum_c y_ic log p_ic`` with ``p`` clipped.

Two dependency-free renderers are provided for the headline artifact: an SVG
reliability diagram (:func:`reliability_svg`) and a compact ASCII curve
(:func:`ascii_curve`). Both are deterministic and tolerate empty inputs.
"""

from __future__ import annotations

import math

EPS = 1e-12
DEFAULT_BINS = 10


def _clip(p: float) -> float:
    """Clip a probability into ``[EPS, 1-EPS]`` so logs stay finite."""

    return min(max(p, EPS), 1.0 - EPS)


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def _edges(bins: int) -> list[float]:
    """Equal-width bin edges over ``[0, 1]``; there are ``bins + 1`` edges."""

    n = max(1, int(bins))
    return [i / n for i in range(n + 1)]


def _in_bin(p: float, lower: float, upper: float, is_last: bool) -> bool:
    if is_last:
        return lower <= p <= upper
    return lower <= p < upper


def brier_score(pairs: list[tuple[float, float]]) -> float:
    """Binary Brier over ``(probability, outcome)`` pairs. Empty -> 0.0."""

    if not pairs:
        return 0.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: list[tuple[float, float]]) -> float:
    """Binary log loss (natural log). Empty -> 0.0."""

    if not pairs:
        return 0.0
    total = 0.0
    for p, y in pairs:
        q = _clip(p)
        total -= y * math.log(q) + (1.0 - y) * math.log(1.0 - q)
    return total / len(pairs)


def expected_calibration_error(pairs: list[tuple[float, float]], bins: int = 10) -> float:
    """ECE over equal-width bins. Empty -> 0.0.

    Rounded to 12 decimals so a hand-check like ``0.2`` compares exactly while
    staying far below any meaningful uncertainty.
    """

    if not pairs:
        return 0.0
    edges = _edges(bins)
    n = len(pairs)
    ece = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        is_last = upper == edges[-1]
        bucket = [(p, y) for p, y in pairs if _in_bin(p, lower, upper, is_last)]
        if not bucket:
            continue
        mean_pred = sum(p for p, _ in bucket) / len(bucket)
        rate = sum(y for _, y in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(mean_pred - rate)
    return round(ece, 12)


def reliability_table(pairs: list[tuple[float, float]], bins: int = 10) -> list[dict]:
    """Per-bin predicted mean, empirical rate, and count.

    Empty input -> ``[]``. Non-empty input yields one row per bin (including
    empty bins, whose means and rates are ``0.0``).
    """

    if not pairs:
        return []
    edges = _edges(bins)
    rows: list[dict] = []
    for index, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        is_last = upper == edges[-1]
        bucket = [(p, y) for p, y in pairs if _in_bin(p, lower, upper, is_last)]
        if bucket:
            mean_pred = sum(p for p, _ in bucket) / len(bucket)
            empirical = sum(y for _, y in bucket) / len(bucket)
        else:
            mean_pred = 0.0
            empirical = 0.0
        rows.append(
            {
                "bin": index,
                "count": len(bucket),
                "mean_predicted": mean_pred,
                "empirical": empirical,
            }
        )
    return rows


def multiclass_brier(dists: list[tuple[dict[str, float], dict[str, float]]]) -> float:
    """Mean over events of ``sum_c (p_c - y_c)^2`` for ``(pred, truth)`` dists."""

    if not dists:
        return 0.0
    total = 0.0
    for pred, truth in dists:
        total += sum((pred.get(label, 0.0) - y) ** 2 for label, y in truth.items())
    return total / len(dists)


def cross_entropy(dists: list[tuple[dict[str, float], dict[str, float]]]) -> float:
    """Mean over events of ``-sum_c y_c log p_c`` for ``(pred, truth)`` dists."""

    if not dists:
        return 0.0
    total = 0.0
    for pred, truth in dists:
        total -= sum(y * math.log(_clip(pred.get(label, 0.0))) for label, y in truth.items())
    return total / len(dists)


def ascii_curve(rows: list[dict], width: int = 40) -> str:
    """Compact text reliability curve: ``#`` empirical, ``o`` perfect."""

    w = max(2, int(width))
    lines = [
        "Calibration curve (predicted p -> empirical rate; '#'=empirical, 'o'=perfect)",
        "  predicted   empirical   count   curve",
    ]
    for row in rows:
        if not row.get("count"):
            continue
        predicted = float(row.get("mean_predicted", 0.0))
        empirical = float(row.get("empirical", 0.0))
        x = min(w - 1, max(0, round(predicted * (w - 1))))
        y = min(w - 1, max(0, round(empirical * (w - 1))))
        track = ["-"] * w
        track[y] = "#"
        if x == y:
            track[y] = "o"
        lines.append(f"  {predicted:9.3f}   {empirical:9.3f}   {int(row['count']):5d}   {''.join(track)}")
    return "\n".join(lines)


def reliability_svg(rows: list[dict], width: int = 640, height: int = 480) -> str:
    """Self-contained SVG reliability diagram (no external deps, deterministic).

    Draws 0..1 axes, the ``y = x`` perfect-calibration diagonal, one bar plus a
    point per non-empty bin (``x`` = mean predicted, ``y`` = empirical rate), a
    legend, and the overall Brier/ECE as text. The table itself carries no Brier,
    so the displayed value is the exact within-bin Brier estimate implied by the
    table (predictions constant at each bin mean).
    """

    w = max(320, int(width))
    h = max(240, int(height))
    pad_l, pad_r, pad_t, pad_b = 64, 24, 40, 56
    x0, x1 = pad_l, w - pad_r
    y0, y1 = pad_t, h - pad_b
    pw, ph = x1 - x0, y1 - y0

    def sx(v: float) -> float:
        return x0 + _clamp01(v) * pw

    def sy(v: float) -> float:
        return y1 - _clamp01(v) * ph

    valid = [r for r in rows if r.get("count")]
    total = sum(int(r["count"]) for r in valid)
    if total:
        ece = sum((r["count"] / total) * abs(r["mean_predicted"] - r["empirical"]) for r in valid)
        brier = sum(
            (r["count"] / total) * ((r["mean_predicted"] - r["empirical"]) ** 2 + r["empirical"] * (1 - r["empirical"]))
            for r in valid
        )
    else:
        ece = 0.0
        brier = 0.0

    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">')
    parts.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>')
    parts.append(
        f'<text x="{x0}" y="24" font-family="sans-serif" font-size="16" font-weight="bold" '
        f'fill="#111111">Reliability diagram</text>'
    )
    parts.append(
        f'<text x="{x1}" y="24" text-anchor="end" font-family="sans-serif" font-size="12" '
        f'fill="#333333">Brier {brier:.4f} · ECE {ece:.4f} · n={total}</text>'
    )
    for i in range(11):
        value = i / 10
        gx, gy = sx(value), sy(value)
        parts.append(f'<line x1="{gx:.2f}" y1="{y0}" x2="{gx:.2f}" y2="{y1}" stroke="#eeeeee" stroke-width="1"/>')
        parts.append(f'<line x1="{x0}" y1="{gy:.2f}" x2="{x1}" y2="{gy:.2f}" stroke="#eeeeee" stroke-width="1"/>')
    parts.append(
        f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y0}" stroke="#888888" stroke-width="1.5" stroke-dasharray="6 4"/>'
    )
    parts.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="#333333" stroke-width="1.5"/>')
    parts.append(f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#333333" stroke-width="1.5"/>')
    for i in range(11):
        value = i / 10
        parts.append(
            f'<text x="{sx(value):.2f}" y="{y1 + 16}" text-anchor="middle" font-family="sans-serif" '
            f'font-size="10" fill="#333333">{value:.1f}</text>'
        )
        parts.append(
            f'<text x="{x0 - 8}" y="{sy(value) + 4:.2f}" text-anchor="end" font-family="sans-serif" '
            f'font-size="10" fill="#333333">{value:.1f}</text>'
        )
    bar_w = max(6.0, min(20.0, pw / max(1, len(rows)) * 0.5))
    for row in valid:
        bx, by = sx(row["mean_predicted"]), sy(row["empirical"])
        parts.append(
            f'<rect x="{bx - bar_w / 2:.2f}" y="{by:.2f}" width="{bar_w:.2f}" '
            f'height="{max(0.0, y1 - by):.2f}" fill="#2f6feb" fill-opacity="0.20" '
            f'stroke="#2f6feb" stroke-opacity="0.5" stroke-width="1"/>'
        )
        parts.append(
            f'<circle cx="{bx:.2f}" cy="{by:.2f}" r="4" fill="#2f6feb" stroke="#ffffff" stroke-width="1"/>'
        )
    lx, ly = x1 - 210, y0 + 12
    parts.append(
        f'<rect x="{lx}" y="{ly}" width="200" height="54" fill="#ffffff" fill-opacity="0.9" '
        f'stroke="#cccccc" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{lx + 10}" y1="{ly + 14}" x2="{lx + 34}" y2="{ly + 14}" stroke="#888888" '
        f'stroke-width="1.5" stroke-dasharray="6 4"/>'
    )
    parts.append(
        f'<text x="{lx + 42}" y="{ly + 18}" font-family="sans-serif" font-size="10" fill="#333333">'
        f'Perfect calibration (y = x)</text>'
    )
    parts.append(
        f'<rect x="{lx + 10}" y="{ly + 26}" width="18" height="10" fill="#2f6feb" fill-opacity="0.20" '
        f'stroke="#2f6feb" stroke-opacity="0.5" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{lx + 42}" y="{ly + 35}" font-family="sans-serif" font-size="10" fill="#333333">'
        f'Empirical rate per bin</text>'
    )
    parts.append(f'<circle cx="{lx + 19}" cy="{ly + 45}" r="4" fill="#2f6feb" stroke="#ffffff" stroke-width="1"/>')
    parts.append(
        f'<text x="{lx + 42}" y="{ly + 49}" font-family="sans-serif" font-size="10" fill="#333333">'
        f'Bin (mean predicted)</text>'
    )
    parts.append(
        f'<text x="{(x0 + x1) / 2:.2f}" y="{h - 14}" text-anchor="middle" font-family="sans-serif" '
        f'font-size="12" fill="#333333">mean predicted probability</text>'
    )
    mid_y = (y0 + y1) / 2
    parts.append(
        f'<text x="16" y="{mid_y:.2f}" text-anchor="middle" transform="rotate(-90 16 {mid_y:.2f})" '
        f'font-family="sans-serif" font-size="12" fill="#333333">empirical rate</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)
