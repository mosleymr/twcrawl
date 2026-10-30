from __future__ import annotations

import http.server
import json
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

from .api import api_response
from .storage import latest_run


def make_server(host: str, port: int, *, database: Path, out: Path, api_only: bool = False) -> http.server.ThreadingHTTPServer:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            super().end_headers()

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            self.read_request()

        def do_HEAD(self) -> None:
            self.read_request(head=True)

        def do_POST(self) -> None:
            self.send_json(405, {"error": "read-only API"})

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

        def read_request(self, *, head: bool = False) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api" or parsed.path.startswith("/api/"):
                try:
                    run = latest_run(database)
                    if run is None:
                        self.send_json(503, {"error": "no stored crawl yet; run twcrawl archive or crawl"}, head=head)
                        return
                    status, payload = api_response(run["data"], parsed.path, parsed.query, database=database)
                except Exception:
                    self.send_json(503, {"error": "stored crawl data unavailable"}, head=head)
                    return
                self.send_json(status, payload, head=head)
            elif api_only:
                self.send_json(404, {"error": "not found"}, head=head)
            elif head:
                super().do_HEAD()
            else:
                super().do_GET()

        def send_json(self, status: int, payload: dict, *, head: bool = False) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)

    server = http.server.ThreadingHTTPServer((host, port), partial(Handler, directory=str(out)))
    server.daemon_threads = True
    return server


def serve(database: Path, out: Path, *, host: str, port: int, api_only: bool = False) -> int:
    with make_server(host, port, database=database, out=out, api_only=api_only) as server:
        print(f"serving http://{host}:{server.server_port}/api from {database}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
