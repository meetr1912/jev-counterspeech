"""Egress safety tests: no socket I/O, no outbound client, and one local write path.

The server's no-network guarantee is structural: no HTTP client reaches an external
host anywhere in the review UI, the sole write path (:func:`server._handle_outbox`)
appends one JSON line to a local file and touches nothing else, and the server
refuses to bind anything but a loopback address. These tests fail if any of those
properties is weakened.
"""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

from jev_counterspeech import server

FORBIDDEN = (
    "urllib.request",
    "http.client",
    "requests.",
    "urlopen",
    "HTTPConnection",
    "socket.",
)

FORBIDDEN_IMPORTS = ("httpx", "requests", "urllib.request", "http.client", "socket")


def _source_files():
    root = Path(server.__file__).resolve().parent
    yield root / "server.py"
    yield root / "cli.py"
    for path in sorted((root / "static").rglob("*")):
        if path.is_file():
            yield path


def _imported_modules(source: str) -> set[str]:
    """Every top-level module name imported by ``source`` (docstrings excluded)."""

    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_server_and_static_have_no_outbound_client():
    server_path = Path(server.__file__).resolve().parent / "server.py"
    server_source = server_path.read_text(encoding="utf-8")
    for module in _imported_modules(server_source):
        assert not any(
            module == banned or module.startswith(f"{banned}.") for banned in FORBIDDEN_IMPORTS
        ), f"server.py imports outbound client {module!r}"

    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        for identifier in FORBIDDEN:
            assert identifier not in source, f"{path.name} contains {identifier!r}"


def test_server_outbox_handler_makes_no_network_call(monkeypatch, tmp_path):
    def _no_network(*args, **kwargs):
        raise AssertionError("the outbox write path must not touch the network")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)

    status, body = server._handle_outbox(
        {"approved": True, "text": "a respectful reply", "post_id": "p", "candidate_id": "c1"},
        tmp_path,
        {"p"},
    )

    assert status == 200
    assert body["ok"] is True
    lines = [
        line for line in (tmp_path / "outbox.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(lines) == 1
    assert json.loads(lines[0])["network"] == "none"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"approved": False, "text": "hello", "post_id": "p"}, id="not_approved"),
        pytest.param({"approved": True, "text": "   ", "post_id": "p"}, id="empty_text"),
    ],
)
def test_outbox_payload_guard_rejects_and_writes_nothing(tmp_path, payload):
    status, body = server._handle_outbox(payload, tmp_path, {"p"})

    assert status == 400
    assert "refused" in body["error"]
    assert not (tmp_path / "outbox.jsonl").exists()


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8"], ids=["all_interfaces", "public_dns"])
def test_loopback_bind_enforced(tmp_path, host):
    with pytest.raises(ValueError, match="loopback"):
        server.serve(tmp_path, host=host, port=0)
