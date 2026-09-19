"""Local review server: read API, the single approved write path, loopback only."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from jev_counterspeech import server

HOST = "127.0.0.1"
PORT = 8799
BASE = f"http://{HOST}:{PORT}"


def _minimal_report():
    return {
        "meta": {},
        "calibration": {"brier": 0.0, "ece": 0.0, "count": 0},
        "gate": {
            "draft": 0,
            "human_review": 0,
            "ignore": 0,
            "report": 0,
            "refused": 0,
            "drafted_items": 0,
        },
        "items": [{"post_id": "p", "gate": {}, "candidates": [], "ranking": None}],
    }


def _wait_for_server(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/api/data", timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    raise AssertionError("server did not become ready in time")


def _post(payload):
    request = urllib.request.Request(
        f"{BASE}/api/outbox",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture
def live_server(results_dir):
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "report.json").write_text(json.dumps(_minimal_report()), encoding="utf-8")
    thread = threading.Thread(
        target=server.serve,
        args=(results_dir,),
        kwargs={"host": HOST, "port": PORT},
        daemon=True,
    )
    thread.start()
    try:
        _wait_for_server()
        yield results_dir
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


def test_get_api_data_returns_items(live_server):
    with urllib.request.urlopen(f"{BASE}/api/data", timeout=2.0) as response:
        assert response.status == 200
        body = json.loads(response.read().decode("utf-8"))
    assert "items" in body
    assert body["items"][0]["post_id"] == "p"


def test_post_without_approval_is_refused_and_writes_nothing(live_server):
    status, _ = _post({"approved": False, "text": "hello", "post_id": "p"})
    assert 400 <= status < 500
    assert not (live_server / "outbox.jsonl").exists()


def test_post_with_approval_writes_exactly_one_local_line(live_server):
    status, body = _post(
        {"approved": True, "text": "a respectful reply", "post_id": "p", "candidate_id": "c1"}
    )
    assert status == 200
    assert body["count"] == 1
    outbox = (live_server / "outbox.jsonl").read_text(encoding="utf-8").splitlines()
    lines = [line for line in outbox if line.strip()]
    assert len(lines) == 1
    assert '"network": "none"' in lines[0]


def test_post_rejects_empty_text(live_server):
    status, _ = _post({"approved": True, "text": "   ", "post_id": "p"})
    assert 400 <= status < 500
    assert not (live_server / "outbox.jsonl").exists()


def test_serve_refuses_non_loopback_host(results_dir):
    with pytest.raises(ValueError):
        server.serve(results_dir, host="0.0.0.0", port=0)
