#!/usr/bin/env python3
"""Serve the static dashboard from the repository root.

The published dashboard (https://pklavc.com/Autotrader/) is plain HTML/CSS/JS
plus the `data/*.json` files committed by the paper-trade workflow. There is no
build step and no backend, so a local preview only needs a static file server
that:

* binds 0.0.0.0 (not 127.0.0.1) so it works behind a proxy or container;
* answers for any host header, because preview proxies rewrite the Host;
* serves `data/*.json` with `Cache-Control: no-store`, matching how the page
  fetches them, so a preview never shows a stale ledger;
* stays inside the repository root and never follows `..` out of it.

Usage:
    python scripts/serve_static.py --port 4173

Keep it a preview tool only: it has no authentication and must never be exposed
to the public internet; the account dashboard under /account/ is gated by the
fleet API, not by this server.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import sys
from pathlib import Path

CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".gif": "image/gif",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".webp": "image/webp",
}

CACHEABLE_SUFFIXES = {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Directory handler that resolves every request against the repo root."""

    root: Path

    def translate_path(self, path: str) -> str:
        # Drop query strings and fragments before delegating; the base
        # implementation already rejects escapes above the served directory.
        clean = path.split("?", 1)[0].split("#", 1)[0]
        return super().translate_path(clean)

    def end_headers(self) -> None:
        suffix = Path(self.path.split("?", 1)[0].split("#", 1)[0]).suffix.lower()
        if suffix in CACHEABLE_SUFFIXES:
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def guess_type(self, path) -> str:  # type: ignore[override]
        return CONTENT_TYPES.get(Path(path).suffix.lower(), super().guess_type(path))

    def log_message(self, fmt: str, *args) -> None:  # keep preview logs one line each
        sys.stderr.write("[static] %s %s\n" % (self.address_string(), fmt % args))


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=4173, help="TCP port (default: 4173)")
    parser.add_argument("--root", default=str(repo_root), help="directory to serve (default: repo root)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "index.html").is_file():
        parser.error(f"{root} does not contain index.html; run this from the repository root")

    handler = functools.partial(DashboardHandler, directory=str(root))
    DashboardHandler.root = root

    with ThreadingServer((args.host, args.port), handler) as httpd:
        print(f"[static] serving {root} on http://{args.host}:{args.port}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[static] stopped", flush=True)
    return 0


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent.parent)
    raise SystemExit(main())
