"""Local preview of the activity page against roguetw's read-only stored API."""
from __future__ import annotations

import argparse
import http.server
import tempfile
from functools import partial
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from twcrawl.render import STYLE, build_activity_page, copy_assets


class Preview(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/"):
            try:
                with urlopen("https://roguetw.net" + self.path, timeout=30) as response:
                    body = response.read()
                    self.send_response(response.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
            except HTTPError as error:
                self.send_error(error.code)
            except OSError:
                self.send_error(502)
            return
        super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8022)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="twcrawl-activity-preview-") as directory:
        root = Path(directory)
        build_activity_page(root)
        games = root / "games"
        games.mkdir()
        (games / "style.css").write_text(STYLE)
        copy_assets(games)
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), partial(Preview, directory=directory)) as server:
            print(f"http://127.0.0.1:{server.server_port}/active.html", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
