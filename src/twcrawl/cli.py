from __future__ import annotations

import argparse
import http.server
import json
import socketserver
from pathlib import Path
from urllib.parse import urlparse

from .api import api_response
from .crawler import crawl_servers, load_or_seed, save_json
from .importer import DEFAULT_ARCHIVE_URL, write_seed
from .render import build_site


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED = ROOT / "data" / "servers.seed.json"
DEFAULT_DATA = ROOT / "data" / "twcrawl.json"
DEFAULT_PUBLIC = ROOT / "public"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="twcrawl")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-seeds", help="import the archived MicroBlaster TWGS2 server list")
    init.add_argument("--url", default=DEFAULT_ARCHIVE_URL)
    init.add_argument("--out", type=Path, default=DEFAULT_SEED)
    init.add_argument("--force", action="store_true", help="overwrite an existing seed file")

    crawl = sub.add_parser("crawl", help="crawl TWGS servers and update JSON data")
    crawl.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    crawl.add_argument("--data", type=Path, default=DEFAULT_DATA)
    crawl.add_argument("--only")
    crawl.add_argument("--limit", type=int)
    crawl.add_argument("--all", action="store_true")
    crawl.add_argument("--missing", action="store_true", help="crawl only servers without current usable data")
    crawl.add_argument("--bot-name", default="twcrawl")
    crawl.add_argument("--connect-timeout", type=float, default=12.0)
    crawl.add_argument("--game-timeout", type=float, default=35.0)
    crawl.add_argument("--build", action="store_true")
    crawl.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)

    build = sub.add_parser("build", help="generate static HTML from JSON data")
    build.add_argument("--data", type=Path, default=DEFAULT_DATA)
    build.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    build.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)

    serve_parser = sub.add_parser("serve", help="serve generated static pages")
    serve_parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    serve_parser.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    serve_parser.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)
    serve_parser.add_argument("--port", type=int, default=8008)

    args = parser.parse_args(argv)
    if args.command == "init-seeds":
        try:
            data = write_seed(args.out, args.url, overwrite=args.force)
        except FileExistsError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"wrote {len(data['servers'])} servers to {args.out}")
        return 0
    if args.command == "crawl":
        if not args.all and not args.only and not args.missing and args.limit is None:
            raise SystemExit("use --all, --only, --missing, or --limit so a crawl is intentional")
        data = load_or_seed(args.data, args.seeds)
        data = crawl_servers(
            data,
            only=args.only,
            missing=args.missing,
            limit=args.limit,
            bot_name=args.bot_name,
            connect_timeout=args.connect_timeout,
            game_timeout=args.game_timeout,
        )
        save_json(args.data, data)
        print(f"wrote {args.data}")
        if args.build:
            build_site(data, args.out)
            print(f"built {args.out}")
        return 0
    if args.command == "build":
        data = load_or_seed(args.data, args.seeds)
        build_site(data, args.out)
        print(f"built {args.out}")
        return 0
    if args.command == "serve":
        return serve_site(args.out, args.port, args.data, args.seeds)
    return 1


def serve_site(out: Path, port: int, data_path: Path, seed_path: Path) -> int:
    class TwcrawlHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(out), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            super().end_headers()

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if (parsed.path == "/api" or parsed.path.startswith("/api/")) and not parsed.path.endswith(".json"):
                self.serve_api(parsed.path, parsed.query)
                return
            super().do_GET()

        def serve_api(self, path: str, query: str) -> None:
            try:
                data = load_or_seed(data_path, seed_path)
                status, payload = api_response(data, path, query)
            except Exception as exc:
                status = 500
                payload = {"error": str(exc)}
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with ReusableTCPServer(("127.0.0.1", port), TwcrawlHandler) as httpd:
        print(f"serving http://127.0.0.1:{port}/ from {out}")
        print(f"api http://127.0.0.1:{port}/api using {data_path}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
