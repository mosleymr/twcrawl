from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .crawler import add_server, crawl_servers, load_json, load_or_seed, save_json
from .history import snapshot_data
from .importer import DEFAULT_ARCHIVE_URL, write_seed
from .mtc_monitor import DEFAULT_MTC_GAMES_DIR, dumps_monitor_report, format_monitor_report, monitor_recent_mtc_games
from .online import check_player_online, dumps_online_report, format_online_report
from .render import build_site
from .search import dumps_search_results, format_search_results, search_games
from .storage import archive_data, latest_run, read_runs


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

    serve_parser = sub.add_parser("serve", help="serve the SQLite-backed API and optional static pages")
    serve_parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    serve_parser.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    serve_parser.add_argument("--out", type=Path, default=DEFAULT_PUBLIC)
    serve_parser.add_argument("--port", type=int, default=8008)
    serve_parser.add_argument("--host", default="127.0.0.1", help="bind address; keep loopback behind Apache")
    serve_parser.add_argument("--api-only", action="store_true", help="serve only the stored-data API")

    archive = sub.add_parser("archive", help="import existing crawl JSON into SQLite without crawling")
    archive.add_argument("--data", type=Path, default=DEFAULT_DATA)
    archive.add_argument("--seeds", type=Path, default=DEFAULT_SEED)
    report = sub.add_parser("report", help="print a stored crawl report without connecting to game servers")
    report.add_argument("--data", type=Path, default=DEFAULT_DATA)
    report.add_argument("--run", type=int, help="historical run ID; latest by default")

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

    for command in (crawl, daily, add, serve_parser, archive, report):
        command.add_argument("--database", type=Path, help="SQLite archive path; defaults beside --data as twcrawl.sqlite3")
    args = parser.parse_args(argv)
    if hasattr(args, "database"):
        args.database = args.database or args.data.with_suffix(".sqlite3")
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
            before = copy.deepcopy(data)
            data = crawl_servers(
                data,
                only=str(server.get("server_id") or server.get("slug") or server.get("name")),
                missing=False,
                limit=None,
                bot_name=args.bot_name,
                connect_timeout=args.connect_timeout,
                game_timeout=args.game_timeout,
            )
            data = archive_data(data, args.database, baseline=before)
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
        before = copy.deepcopy(data)
        data = crawl_servers(
            data,
            only=args.only,
            missing=args.missing,
            limit=args.limit,
            bot_name=args.bot_name,
            connect_timeout=args.connect_timeout,
            game_timeout=args.game_timeout,
        )
        data = archive_data(data, args.database, baseline=before)
        save_json(args.data, data)
        print(f"wrote {args.data}")
        if args.build:
            build_site(data, args.out)
            print(f"built {args.out}")
        return 0
    if args.command == "daily":
        data = load_or_seed(args.data, args.seeds)
        before = copy.deepcopy(data)
        data = crawl_servers(
            data,
            only=args.only,
            missing=args.mode == "missing",
            limit=args.limit,
            bot_name=args.bot_name,
            connect_timeout=args.connect_timeout,
            game_timeout=args.game_timeout,
        )
        data = archive_data(data, args.database, kind="daily", baseline=before)
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
        from .server import serve
        if latest_run(args.database) is None:
            if not args.data.exists():
                raise SystemExit("no crawl data; run twcrawl crawl or archive first")
            archive_data(load_json(args.data), args.database, kind="import")
        return serve(args.database, args.out, host=args.host, port=args.port, api_only=args.api_only)
    if args.command == "archive":
        if not args.data.exists():
            raise SystemExit(f"crawl data does not exist: {args.data}")
        data = archive_data(load_json(args.data), args.database, kind="import")
        save_json(args.data, data)
        print(f"archived run {data['run_id']} in {args.database}")
        return 0
    if args.command == "report":
        if args.run is not None:
            rows = read_runs(args.database, run_id=args.run)
            payload = rows[0]["report"] if rows else None
        else:
            run = latest_run(args.database)
            payload = run["data"].get("latest_report") if run else None
        if payload is None:
            raise SystemExit("no stored report found")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
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
    from .server import serve

    database = data_path.with_suffix(".sqlite3")
    if latest_run(database) is None:
        archive_data(load_or_seed(data_path, seed_path), database, kind="import")
    return serve(database, out, host="127.0.0.1", port=port)


if __name__ == "__main__":
    raise SystemExit(main())
