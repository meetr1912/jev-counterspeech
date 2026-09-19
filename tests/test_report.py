"""Report artifacts and the report.json contract consumed by the review UI."""

import json
import math

from jev_counterspeech import pipeline, report


def _write(results_dir):
    result = pipeline.run(offline=True, limit=12)
    paths = report.write_results(result.examples, result.items, result.meta, results_dir)
    return result, paths


def test_write_results_creates_all_artifacts(results_dir):
    _, paths = _write(results_dir)
    assert (results_dir / "report.json").is_file()
    assert (results_dir / "REPORT.md").is_file()
    assert (results_dir / "reliability.svg").is_file()
    assert (results_dir / "reliability.txt").is_file()
    assert set(paths) == {"report_json", "report_md", "reliability_svg", "reliability_txt"}


def test_report_json_contract(results_dir):
    _write(results_dir)
    payload = json.loads((results_dir / "report.json").read_text(encoding="utf-8"))

    assert set(payload) == {"meta", "calibration", "gate", "items"}

    calibration = payload["calibration"]
    assert math.isfinite(calibration["brier"])
    assert 0.0 <= calibration["brier"] <= 1.0
    assert math.isfinite(calibration["ece"])
    assert 0.0 <= calibration["ece"] <= 1.0

    assert set(payload["gate"]) == {
        "draft",
        "human_review",
        "ignore",
        "report",
        "refused",
        "drafted_items",
    }

    assert payload["items"]
    for item in payload["items"]:
        assert isinstance(item, dict)
        for key in ("gate", "candidates", "ranking"):
            assert key in item


def test_report_markdown_mentions_calibration_and_responsible_use(results_dir):
    _write(results_dir)
    markdown = (results_dir / "REPORT.md").read_text(encoding="utf-8").lower()
    assert "calibration" in markdown
    assert "responsible use" in markdown
