"""Local-only review UI for jev-counterspeech.

This module serves a dependency-free inspector for a completed run's
``report.json`` and it is the *only* thing in the project that can write a
"send" decision. That write goes to a local file, ``<results_dir>/outbox.jsonl``.

NO-NETWORK GUARANTEE
--------------------
There is no posting, no X/Twitter API, no browser automation, and no outbound
request of any kind in this module. The server binds a loopback address only and
the sole write path (:func:`_handle_outbox`) appends one JSON line to a file on
disk. Nothing here opens a socket to an external host; ``urllib`` is never
imported for outbound use, and the client-facing routes only read local files.

Standard library only: ``http.server``, ``json``, ``pathlib`` (plus ``datetime``
and ``urllib.parse``).
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

#: Only these static extensions are ever served.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".html", ".js", ".css", ".svg", ".ico", ".map", ".txt", ".json"})

MIME_TYPES: dict[str, str] = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".map": "application/json",
    ".txt": "text/plain",
    ".json": "application/json",
}

#: Set by :func:`serve` so a caller (or test) can request a clean shutdown.
_SERVER: ThreadingHTTPServer | None = None

MAX_BODY_BYTES = 32 * 1024
MAX_TEXT_CHARS = 2000
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


# --------------------------------------------------------------------------- #
# Local file helpers
# --------------------------------------------------------------------------- #


def _report_path(results_dir: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(results_dir) / "report.json"


def load_report(results_dir: str | pathlib.Path) -> dict | None:
    """Read ``report.json`` fresh; return ``None`` when missing or malformed."""

    try:
        return json.loads(_report_path(results_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def known_post_ids(report: dict | None) -> set[str]:
    """The set of ``post_id`` values a run produced (used to reject typos)."""

    ids: set[str] = set()
    if not isinstance(report, dict):
        return ids
    items = report.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("post_id"), str):
                ids.add(item["post_id"])
    return ids


def _outbox_path(results_dir: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(results_dir) / "outbox.jsonl"


def count_outbox(results_dir: str | pathlib.Path) -> int:
    """Number of non-empty records already in the outbox."""

    count = 0
    try:
        with _outbox_path(results_dir).open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
    except OSError:
        return 0
    return count


def read_outbox(results_dir: str | pathlib.Path) -> list[dict]:
    """Parse the outbox as JSON lines. Unparseable lines are surfaced verbatim."""

    records: list[dict] = []
    try:
        with _outbox_path(results_dir).open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    records.append({"raw": line})
    except OSError:
        return []
    return records


def _handle_outbox(
    payload: object,
    results_dir: str | pathlib.Path,
    post_ids: set[str],
) -> tuple[int, dict]:
    """Validate and (only if approved) append one record to the local outbox.

    Returns ``(http_status, response_body)``. This is the single write path in
    the whole UI and it touches nothing but ``<results_dir>/outbox.jsonl``.
    Exposed with a leading underscore so tests can import and call it directly.
    """

    if not isinstance(payload, dict):
        return 400, {"error": "body must be a JSON object"}

    if payload.get("approved") is not True:
        return 400, {"error": "refused: 'approved' must be true; nothing was written"}

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return 400, {"error": "refused: 'text' must be a non-empty string"}
    if len(text) > MAX_TEXT_CHARS:
        return 400, {"error": f"refused: 'text' exceeds {MAX_TEXT_CHARS} characters"}

    post_id = payload.get("post_id")
    if post_id not in post_ids:
        return 400, {"error": f"refused: unknown post_id {post_id!r}"}

    candidate_id = payload.get("candidate_id")
    record = {
        "post_id": post_id,
        "candidate_id": candidate_id,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "network": "none",
    }

    results_dir = pathlib.Path(results_dir)
    outbox = _outbox_path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    with outbox.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return 200, {"ok": True, "path": str(outbox), "count": count_outbox(results_dir)}


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #


class Handler(BaseHTTPRequestHandler):
    """Serve the static UI and the small read/write JSON API."""

    results_dir: pathlib.Path = pathlib.Path(".")
    server_version = "jev-counterspeech-review/0.1"
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------- #

    def _local_request(self) -> bool:
        host = self.headers.get("Host", "").strip()
        name = host.split(":")[0].strip("[]")
        return name in LOOPBACK_HOSTS or name == ""

    def _send(self, status: int, content: bytes | str, mime: str = "application/json") -> None:
        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, obj: object) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _serve_static(self, name: str, mime: str | None = None) -> None:
        if not name or name.startswith("/") or "\\" in name:
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        parts = pathlib.PurePosixPath(name).parts
        if any(part in ("..", "") for part in parts):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        suffix = pathlib.Path(name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        try:
            target = (STATIC_DIR / name).resolve()
            target.relative_to(STATIC_DIR)
        except (OSError, ValueError):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        if not target.is_file():
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        content_type = mime or MIME_TYPES.get(suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), content_type + "; charset=utf-8")

    # -- routes ------------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802
        if not self._local_request():
            return self._send(403, "Forbidden: local only", "text/plain; charset=utf-8")
        path = urlparse(self.path).path
        if path == "/":
            return self._serve_static("index.html", "text/html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/api/data":
            report = load_report(self.results_dir)
            if report is None:
                return self._send_json(404, {"error": "report.json not found or invalid"})
            return self._send_json(200, report)
        if path == "/api/outbox":
            return self._send_json(200, read_outbox(self.results_dir))
        return self._send(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if not self._local_request():
            return self._send(403, json.dumps({"error": "local only"}))
        path = urlparse(self.path).path
        if path != "/api/outbox":
            return self._send_json(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send_json(400, {"error": "invalid Content-Length"})
        if length <= 0 or length > MAX_BODY_BYTES:
            return self._send_json(400, {"error": "empty or oversized body"})
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._send_json(400, {"error": "invalid JSON body"})
        report = load_report(self.results_dir)
        status, body = _handle_outbox(payload, self.results_dir, known_post_ids(report))
        return self._send_json(status, body)

    def log_message(self, *_args) -> None:
        pass


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def serve(results_dir: str | pathlib.Path, host: str = "127.0.0.1", port: int = 8781) -> None:
    """Serve the review UI for ``<results_dir>/report.json`` on loopback.

    Blocks until interrupted or :func:`shutdown` is called. Only a loopback host
    is accepted: the server must never be reachable off the local machine.
    """

    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"refusing to bind non-loopback host {host!r}; local review only")

    global _SERVER
    results_dir = pathlib.Path(results_dir)
    Handler.results_dir = results_dir
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    _SERVER = httpd
    print(f"jev-counterspeech review UI: http://{host}:{port}  (results: {results_dir})", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        _SERVER = None


def shutdown() -> None:
    """Stop a server started by :func:`serve` (used by tests and Ctrl-C paths)."""

    global _SERVER
    if _SERVER is not None:
        _SERVER.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve the local jev-counterspeech review UI.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8781)
    args = parser.parse_args()
    serve(args.results_dir, args.host, args.port)
