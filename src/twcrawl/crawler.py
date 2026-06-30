from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .parser import parse_game_stats, parse_server_menu
from .telnet import TelnetError, TelnetSession


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"generated_at": None, "servers": []}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_or_seed(data_path: Path, seed_path: Path) -> dict:
    if data_path.exists():
        return load_json(data_path)
    data = load_json(seed_path)
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    return data


def crawl_servers(
    data: dict,
    *,
    only: str | None = None,
    limit: int | None = None,
    bot_name: str = "twcrawl",
    connect_timeout: float = 12.0,
    game_timeout: float = 35.0,
) -> dict:
    selected = select_servers(data.get("servers", []), only=only, limit=limit)
    for server in selected:
        print(f"crawl {server.get('name')} {server.get('telnet')}")
        try:
            live = crawl_server(
                server,
                bot_name=bot_name,
                connect_timeout=connect_timeout,
                game_timeout=game_timeout,
            )
            server.update(live)
            server["status"] = "online"
            server.pop("error", None)
        except Exception as exc:
            server["status"] = "error"
            server["error"] = str(exc)
            server["last_crawled_at"] = datetime.now(timezone.utc).isoformat()
            print(f"  error: {exc}")
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    summarize_servers(data)
    return data


def select_servers(servers: list[dict], *, only: str | None, limit: int | None) -> list[dict]:
    result = servers
    if only:
        needle = only.lower()
        result = [
            server
            for server in servers
            if needle in server.get("name", "").lower()
            or needle == str(server.get("server_id", "")).lower()
            or needle == server.get("slug", "").lower()
        ]
        if not result:
            raise ValueError(f"no server matched {only!r}")
    if limit is not None:
        result = result[:limit]
    return result


def crawl_server(
    server: dict,
    *,
    bot_name: str = "twcrawl",
    connect_timeout: float = 12.0,
    game_timeout: float = 35.0,
) -> dict:
    host, port = parse_telnet_address(server["telnet"])
    crawl_time = datetime.now(timezone.utc)
    with TelnetSession(host, port, connect_timeout=connect_timeout) as telnet:
        telnet.wait_for("Please enter your name", timeout=connect_timeout)
        telnet.send_line(bot_name)
        menu_start = len(telnet.text)
        menu = telnet.wait_for("Selection (? for menu):", timeout=20.0)
        server_info = parse_server_menu(menu)
        games = server_info.pop("menu_games", [])

        crawled_games: list[dict] = []
        for game in games:
            game_start = len(telnet.text)
            telnet.send_line(game["letter"])
            try:
                telnet.wait_for("Enter your choice:", timeout=game_timeout, auto_pause=True, since=game_start)
            except TelnetError as exc:
                crawled_games.append({**game, "status": "error", "error": str(exc)})
                recover_to_menu(telnet)
                continue

            stats_start = len(telnet.text)
            telnet.send_line("*")
            try:
                stats_text = telnet.wait_for("Enter your choice:", timeout=game_timeout, since=stats_start)
                parsed = parse_game_stats(stats_text, crawl_time)
                crawled_games.append({**game, **parsed, "status": "ok"})
            except TelnetError as exc:
                crawled_games.append({**game, "status": "error", "error": str(exc)})

            exit_start = len(telnet.text)
            telnet.send_line("X")
            try:
                telnet.wait_for("Selection (? for menu):", timeout=20.0, since=exit_start)
            except TelnetError:
                break

        try:
            telnet.send_line("Q")
        except Exception:
            pass

    server_info["games"] = sorted(crawled_games, key=lambda g: g.get("letter", ""))
    server_info["game_count"] = len(crawled_games)
    server_info["players"] = max((g.get("players") or 0 for g in crawled_games), default=0)
    server_info["last_bigbang"] = latest_bigbang(crawled_games)
    server_info["last_crawled_at"] = crawl_time.isoformat()
    server_info["crawl_transcript"] = menu[0:0]
    return server_info


def recover_to_menu(telnet: TelnetSession) -> None:
    for command in ("X", "Q", ""):
        start = len(telnet.text)
        telnet.send_line(command)
        try:
            telnet.wait_for("Selection (? for menu):", timeout=8.0, since=start)
            return
        except TelnetError:
            continue


def summarize_servers(data: dict) -> None:
    for server in data.get("servers", []):
        games = server.get("games") or []
        if games:
            server["game_count"] = len(games)
            server["players"] = max((game.get("players") or 0 for game in games), default=0)
            server["last_bigbang"] = latest_bigbang(games) or server.get("last_bigbang", "")


def latest_bigbang(games: list[dict]) -> str:
    dates = []
    for game in games:
        value = game.get("bigbang")
        if not value:
            continue
        try:
            dates.append(datetime.strptime(value, "%m/%d/%Y"))
        except ValueError:
            pass
    if not dates:
        return ""
    return max(dates).strftime("%m/%d/%Y")


def parse_telnet_address(value: str) -> tuple[str, int]:
    value = value.strip()
    if "://" in value:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        port = parsed.port or 23
    else:
        host, _, port_text = value.rpartition(":")
        if not host:
            host = port_text
            port = 23
        else:
            port = int(port_text or "23")
    if not host:
        raise ValueError(f"invalid telnet address {value!r}")
    return host, port


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "server"

