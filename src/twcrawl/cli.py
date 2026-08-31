from __future__ import annotations

import argparse
import http.server
import json
import socketserver
from pathlib import Path
from urllib.parse import urlparse

from .api import api_response
from .crawler import add_server, crawl_servers, load_json, load_or_seed, save_json
from .history import snapshot_data
from .importer import DEFAULT_ARCHIVE_URL, write_seed
from .mtc_monitor import DEFAULT_MTC_GAMES_DIR, dumps_monitor_report, format_monitor_report, monitor_recent_mtc_games
from .online import check_player_online, dumps_online_report, format_online_report
from .render import build_site
from .search import dumps_search_results, format_search_results, search_games


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED = ROOT / "data" / "servers.seed.json"
DEFAULT_DATA = ROOT / "data" / "twcrawl.json"
DEFAULT_PUBLIC = ROOT / "public"
DEFAULT_HISTORY = ROOT / "data" / "history"
DEFAULT_MTC_MONITOR_STATE = ROOT / "data" / "monitors" / "mtc-recent.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="twcrawl")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-seeds", help="import the archived MicroBlaster TWGS2 server list")
    init.add_argument("--url", default=DEFAULT_ARCHIVE_URL)
    init.add_argument("--out", type=Path, default=DEFAULT_SEED)
    init.add_argument("--force", action="store_true", help="overwrite an existing seed file")

    add = sub.add_parser("add-server", help="add or update a TWGS server in the local server list")
    add.add_argument("host", help="server IP address or hostname")
    add.add_argument("port", type=int, help="telnet port")
    add.add_argument("name", nargs="+", help="server display name")
    add.add_argument("--data", type=Path, default=DEFAULT_DATA)
    add.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    add.add_argument("--no-seeds", action="store_true", help="update only the active data file")
    add.add_argument("--crawl", action="store_true", help="crawl this server immediately after adding it")
    add.add_argument("--bot-name", default="twcrawl")
    add.add_argument("--connect-timeout", type=float, default=12.0)
    add.add_argument("--game-timeout", type=float, default=35.0)
    add.add_argument("--build", action="store_true", help="rebuild public output after adding or crawling")
    add.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)

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

    daily = sub.add_parser("daily", help="run the normal daily crawl, build output, and store a history snapshot")
    daily.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    daily.add_argument("--data", type=Path, default=DEFAULT_DATA)
    daily.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    daily.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)
    daily.add_argument("--mode", choices=("all", "missing"), default="all")
    daily.add_argument("--only")
    daily.add_argument("--limit", type=int)
    daily.add_argument("--bot-name", default="twcrawl")
    daily.add_argument("--connect-timeout", type=float, default=12.0)
    daily.add_argument("--game-timeout", type=float, default=35.0)
    daily.add_argument("--no-build", action="store_true", help="crawl and snapshot without rebuilding public output")

    build = sub.add_parser("build", help="generate static HTML from JSON data")
    build.add_argument("--data", type=Path, default=DEFAULT_DATA)
    build.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    build.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)

    serve_parser = sub.add_parser("serve", help="serve generated static pages")
    serve_parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    serve_parser.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    serve_parser.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)
    serve_parser.add_argument("--port", type=int, default=8008)

    online = sub.add_parser("online", help="check whether a known player is currently logged in")
    online.add_argument("player", help="player name or generated player slug")
    online.add_argument("--data", type=Path, default=DEFAULT_DATA)
    online.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    online.add_argument("--bot-name", default="twcrawl")
    online.add_argument("--connect-timeout", type=float, default=12.0)
    online.add_argument("--menu-timeout", type=float, default=20.0)
    online.add_argument("--json", action="store_true", help="write machine-readable JSON")

    search = sub.add_parser("search", help="search crawled games by text/edit name and/or active player name")
    search.add_argument("query", nargs="?", default="", help="text to match against server, game, edit/config, and stats fields")
    search.add_argument("--edit", dest="edit", help="alias for query; useful for edit/template names such as SubZero")
    search.add_argument("--player", help="active player name substring")
    search.add_argument("--server", help="server id, slug, or name substring")
    search.add_argument("--status", help="game status filter, such as ok")
    search.add_argument("--limit", type=int)
    search.add_argument("--data", type=Path, default=DEFAULT_DATA)
    search.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    search.add_argument("--json", action="store_true", help="write machine-readable JSON")

    monitor = sub.add_parser("monitor-mtc", help="check recent MTC games for new high-score players and live online users")
    monitor.add_argument("--data", type=Path, default=DEFAULT_DATA)
    monitor.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    monitor.add_argument("--mtc-games-dir", type=Path, default=DEFAULT_MTC_GAMES_DIR)
    monitor.add_argument("--days", type=int, default=60)
    monitor.add_argument("--state", type=Path, default=DEFAULT_MTC_MONITOR_STATE)
    monitor.add_argument("--bot-name", default="twcrawl")
    monitor.add_argument("--connect-timeout", type=float, default=12.0)
    monitor.add_argument("--menu-timeout", type=float, default=20.0)
    monitor.add_argument("--no-live", action="store_true", help="skip live # online checks and only compare crawled players")
    monitor.add_argument("--no-save", action="store_true", help="do not update monitor state after reporting")
    monitor.add_argument("--json", action="store_true", help="write machine-readable JSON")

    args = parser.parse_args(argv)
    if args.command == "init-seeds":
        try:
            data = write_seed(args.out, args.url, overwrite=args.force)
        except FileExistsError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"wrote {len(data['servers'])} servers to {args.out}")
        return 0
    if args.command == "add-server":
        name = " ".join(args.name)
        data = load_or_seed(args.data, args.seeds)
        data, action, server = add_server(data, host=args.host, port=args.port, name=name)
        save_json(args.data, data)
        print(f"{action} {server['name']} {server['telnet']} in {args.data}")

        if not args.no_seeds:
            seed_data = load_json(args.seeds)
            seed_data, seed_action, seed_server = add_server(seed_data, host=args.host, port=args.port, name=name)
            save_json(args.seeds, seed_data)
            print(f"{seed_action} {seed_server['name']} {seed_server['telnet']} in {args.seeds}")

        if args.crawl:
            data = crawl_servers(
                data,
                only=str(server.get("server_id") or server.get("slug") or server.get("name")),
                missing=False,
                limit=None,
                bot_name=args.bot_name,
                connect_timeout=args.connect_timeout,
                game_timeout=args.game_timeout,
            )
            save_json(args.data, data)
            print(f"wrote {args.data}")

        if args.build:
            build_site(data, args.out)
            print(f"built {args.out}")
        elif not args.crawl:
            print(f"next: twcrawl crawl --only {json.dumps(server['name'])} --build")
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
    if args.command == "daily":
        data = load_or_seed(args.data, args.seeds)
        data = crawl_servers(
            data,
            only=args.only,
            missing=args.mode == "missing",
            limit=args.limit,
            bot_name=args.bot_name,
            connect_timeout=args.connect_timeout,
            game_timeout=args.game_timeout,
        )
        save_json(args.data, data)
        print(f"wrote {args.data}")
        if not args.no_build:
            build_site(data, args.out)
            print(f"built {args.out}")
        snapshot = snapshot_data(data, args.history, label=args.mode)
        print(f"snapshot {snapshot}")
        return 0
    if args.command == "build":
        data = load_or_seed(args.data, args.seeds)
        build_site(data, args.out)
        print(f"built {args.out}")
        return 0
    if args.command == "serve":
        return serve_site(args.out, args.port, args.data, args.seeds)
    if args.command == "online":
        data = load_or_seed(args.data, args.seeds)
        result = check_player_online(
            data,
            args.player,
            bot_name=args.bot_name,
            connect_timeout=args.connect_timeout,
            menu_timeout=args.menu_timeout,
        )
        print(dumps_online_report(result) if args.json else format_online_report(result))
        return 0
    if args.command == "search":
        data = load_or_seed(args.data, args.seeds)
        query = args.edit if args.edit is not None else args.query
        games = search_games(
            data,
            query=query,
            player=args.player or "",
            server=args.server or "",
            status=args.status or "",
            limit=args.limit,
        )
        print(dumps_search_results(games) if args.json else format_search_results(games, player=args.player or ""))
        return 0
    if args.command == "monitor-mtc":
        data = load_or_seed(args.data, args.seeds)
        report = monitor_recent_mtc_games(
            data,
            mtc_games_dir=args.mtc_games_dir,
            days=args.days,
            state_path=args.state,
            live=not args.no_live,
            bot_name=args.bot_name,
            connect_timeout=args.connect_timeout,
            menu_timeout=args.menu_timeout,
            save=not args.no_save,
        )
        print(dumps_monitor_report(report) if args.json else format_monitor_report(report))
        return 0
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
