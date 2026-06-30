from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path

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

    crawl = sub.add_parser("crawl", help="crawl TWGS servers and update JSON data")
    crawl.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    crawl.add_argument("--data", type=Path, default=DEFAULT_DATA)
    crawl.add_argument("--only")
    crawl.add_argument("--limit", type=int)
    crawl.add_argument("--all", action="store_true")
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
    serve_parser.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)
    serve_parser.add_argument("--port", type=int, default=8008)

    args = parser.parse_args(argv)
    if args.command == "init-seeds":
        data = write_seed(args.out, args.url)
        print(f"wrote {len(data['servers'])} servers to {args.out}")
        return 0
    if args.command == "crawl":
        if not args.all and not args.only and args.limit is None:
            raise SystemExit("use --all, --only, or --limit so a crawl is intentional")
        data = load_or_seed(args.data, args.seeds)
        data = crawl_servers(
            data,
            only=args.only,
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
        return serve_site(args.out, args.port)
    return 1


def serve_site(out: Path, port: int) -> int:
    handler = http.server.SimpleHTTPRequestHandler
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("127.0.0.1", port), lambda *a, **kw: handler(*a, directory=str(out), **kw)) as httpd:
        print(f"serving http://127.0.0.1:{port}/ from {out}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
