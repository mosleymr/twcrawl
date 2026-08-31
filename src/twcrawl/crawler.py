from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .parser import (
    parse_game_description_summary,
    parse_game_description_title,
    parse_game_stats,
    parse_high_scores,
    parse_server_menu,
)
from .telnet import TelnetError, TelnetSession


SERVER_MENU_PROMPT_RE = re.compile(r"[:?]\s")
SERVER_MENU_QUIET_SECONDS = 1.5
DESCRIPTION_MENU_PROMPT_RE = re.compile(
    r"(?:Select\s+game|Describe\s+which\s+game).*[:?]\s*$",
    re.IGNORECASE | re.MULTILINE,
)
DESCRIPTION_CONTEXT_RE = re.compile(
    r"(?:Show\s+Game\s+Descriptions|Select\s+game|Describe\s+which\s+game)",
    re.IGNORECASE,
)
DESCRIPTION_PAUSE_MARKERS = ("[Pause]", "[ANY KEY]", "[Any key")


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


def add_server(
    data: dict,
    *,
    host: str,
    port: int,
    name: str,
) -> tuple[dict, str, dict]:
    host = normalize_host(host)
    if not name.strip():
        raise ValueError("server name is required")
    if port < 1 or port > 65535:
        raise ValueError(f"port must be between 1 and 65535, got {port}")

    name = " ".join(name.split())
    telnet = f"{host}:{port}"
    servers = data.setdefault("servers", [])
    target_slug = slugify(name)
    existing = find_existing_server(servers, telnet=telnet, slug=target_slug, name=name)

    if existing is None:
        server_id = unique_server_id(servers, target_slug)
        server = {
            "archived_detail_url": "",
            "bbs": "",
            "game_count": 0,
            "games": [],
            "last_bigbang": "",
            "name": name,
            "players": 0,
            "server_id": server_id,
            "slug": unique_server_slug(servers, target_slug),
            "status": "seed",
            "telnet": telnet,
            "tradewars_version": "",
            "type": "twgs2",
        }
        servers.append(server)
        action = "added"
    else:
        old_telnet = existing.get("telnet")
        existing["name"] = name
        existing["telnet"] = telnet
        existing.setdefault("server_id", unique_server_id(servers, target_slug, exclude=existing))
        existing.setdefault("slug", unique_server_slug(servers, target_slug, exclude=existing))
        existing.setdefault("type", "twgs2")
        existing.setdefault("tradewars_version", "")
        existing.setdefault("last_bigbang", "")
        existing.setdefault("game_count", 0)
        existing.setdefault("players", 0)
        existing.setdefault("games", [])
        if old_telnet != telnet:
            existing["status"] = "seed"
            existing.pop("error", None)
            existing.pop("last_crawled_at", None)
        server = existing
        action = "updated"

    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    return data, action, server


def normalize_host(value: str) -> str:
    host = value.strip()
    if "://" in host:
        parsed = urlparse(host)
        host = parsed.hostname or ""
    elif ":" in host and not host.startswith("["):
        parsed_host, _, parsed_port = host.rpartition(":")
        if parsed_host and parsed_port.isdigit():
            host = parsed_host
    host = host.strip("[]")
    if not host:
        raise ValueError("host is required")
    return host


def find_existing_server(servers: list[dict], *, telnet: str, slug: str, name: str) -> dict | None:
    folded_telnet = telnet.casefold()
    folded_name = name.casefold()
    for server in servers:
        if str(server.get("telnet") or "").casefold() == folded_telnet:
            return server
    for server in servers:
        if str(server.get("slug") or "").casefold() == slug.casefold():
            return server
    for server in servers:
        if str(server.get("name") or "").casefold() == folded_name:
            return server
    return None


def unique_server_id(servers: list[dict], base: str, *, exclude: dict | None = None) -> str:
    used = {str(server.get("server_id") or "") for server in servers if server is not exclude}
    return unique_token(base, used)


def unique_server_slug(servers: list[dict], base: str, *, exclude: dict | None = None) -> str:
    used = {str(server.get("slug") or "") for server in servers if server is not exclude}
    return unique_token(base, used)


def unique_token(base: str, used: set[str]) -> str:
    token = base or "server"
    candidate = token
    index = 2
    while candidate in used:
        candidate = f"{token}-{index}"
        index += 1
    return candidate


def crawl_servers(
    data: dict,
    *,
    only: str | None = None,
    missing: bool = False,
    limit: int | None = None,
    bot_name: str = "twcrawl",
    connect_timeout: float = 12.0,
    game_timeout: float = 35.0,
) -> dict:
    selected = select_servers(data.get("servers", []), only=only, missing=missing, limit=limit)
    if not selected:
        print("no servers selected for crawl")
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


def select_servers(servers: list[dict], *, only: str | None, missing: bool, limit: int | None) -> list[dict]:
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
    if missing:
        result = [server for server in result if needs_current_data(server)]
    if limit is not None:
        result = result[:limit]
    return result


def needs_current_data(server: dict) -> bool:
    games = server.get("games") or []
    if server.get("status") != "online":
        return True
    if not server.get("last_crawled_at"):
        return True
    if not games:
        return True
    return any(game.get("status") != "ok" for game in games)


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
        menu, server_info = wait_for_server_menu(telnet, since=menu_start, timeout=20.0)
        games = server_info.pop("menu_games", [])
        games = enrich_game_names_from_descriptions(telnet, games, timeout=min(game_timeout, 15.0))

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

            game_result = {**game}
            stats_start = len(telnet.text)
            telnet.send_line("*")
            try:
                stats_text = telnet.wait_for("Enter your choice:", timeout=game_timeout, since=stats_start)
                parsed = parse_game_stats(stats_text, crawl_time)
                game_result.update(parsed)
                game_result["status"] = "ok"
            except TelnetError as exc:
                game_result["status"] = "error"
                game_result["error"] = str(exc)

            high_scores_start = len(telnet.text)
            telnet.send_line("H")
            try:
                high_scores_text = telnet.wait_for(
                    "Enter your choice:",
                    timeout=game_timeout,
                    since=high_scores_start,
                    auto_pause=True,
                )
                game_result.update(parse_high_scores(high_scores_text))
            except TelnetError as exc:
                game_result["high_scores_error"] = str(exc)

            crawled_games.append(game_result)

            exit_start = len(telnet.text)
            telnet.send_line("X")
            try:
                wait_for_server_menu(telnet, since=exit_start, timeout=20.0)
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


def wait_for_server_menu(
    telnet: TelnetSession,
    *,
    since: int,
    timeout: float,
    reject_description_menu: bool = False,
) -> tuple[str, dict]:
    deadline = time.monotonic() + timeout
    last_change = time.monotonic()
    last_length = len(telnet.text)
    last_info: dict = {}
    while time.monotonic() < deadline:
        window = telnet.text[since:]
        current_length = len(telnet.text)
        if current_length != last_length:
            last_length = current_length
            last_change = time.monotonic()
        last_info = parse_server_menu(window)
        if last_info.get("menu_games"):
            if reject_description_menu and DESCRIPTION_CONTEXT_RE.search(window):
                telnet.read_available(0.15)
                continue
            if SERVER_MENU_PROMPT_RE.search(window):
                return window, last_info
            if time.monotonic() - last_change >= SERVER_MENU_QUIET_SECONDS:
                return window, last_info
        telnet.read_available(0.15)
    raise TelnetError(
        f"timed out waiting for server menu prompt from {telnet.host}:{telnet.port}; "
        f"identified {len(last_info.get('menu_games', []))} game letters"
    )


def enrich_game_names_from_descriptions(telnet: TelnetSession, games: list[dict], *, timeout: float) -> list[dict]:
    if not games:
        return games

    enriched = [{**game} for game in games]
    description_start = len(telnet.text)
    telnet.send_line("!")
    try:
        description_menu = wait_for_description_menu(telnet, since=description_start, timeout=timeout)
    except TelnetError:
        return enriched
    if description_menu_is_server_menu(description_menu, games):
        return enriched

    summary_names = parse_game_description_summary(description_menu)
    detail_failed = False
    for game in enriched:
        letter = game.get("letter", "")
        detail_name = ""
        if not detail_failed and letter in summary_names:
            detail_start = len(telnet.text)
            telnet.send_line(letter)
            try:
                detail_text = wait_for_description_menu(telnet, since=detail_start, timeout=timeout)
                detail_name = parse_game_description_title(detail_text, letter)
            except TelnetError:
                detail_failed = True
        overlay_name = detail_name or summary_names.get(letter, "")
        if overlay_name:
            game["menu_name"] = game.get("name", "")
            game["name"] = overlay_name
            game["name_source"] = "description_detail" if detail_name else "description_summary"

    return_to_server_menu_from_descriptions(telnet, timeout=timeout)
    return enriched


def description_menu_is_server_menu(text: str, games: list[dict]) -> bool:
    info = parse_server_menu(text)
    menu_letters = {game.get("letter") for game in info.get("menu_games", [])}
    expected_letters = {game.get("letter") for game in games}
    if not menu_letters or menu_letters != expected_letters:
        return False
    if re.search(r"Selection\s*\(\?\s*for\s*menu\)\s*:\s*$", text, re.IGNORECASE | re.MULTILINE):
        return True
    return bool(SERVER_MENU_PROMPT_RE.search(text) and "<!>" in text)


def wait_for_description_menu(telnet: TelnetSession, *, since: int, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    last_change = time.monotonic()
    last_length = len(telnet.text)
    pause_ack_at = -1
    while time.monotonic() < deadline:
        window = telnet.text[since:]
        current_length = len(telnet.text)
        if current_length != last_length:
            last_length = current_length
            last_change = time.monotonic()
        if DESCRIPTION_MENU_PROMPT_RE.search(window):
            return window
        pause_at = max(window.rfind(marker) for marker in DESCRIPTION_PAUSE_MARKERS)
        if pause_at >= 0 and pause_at != pause_ack_at:
            pause_ack_at = pause_at
            telnet.send_line()
        if window.strip() and time.monotonic() - last_change >= 1.5:
            return window
        telnet.read_available(0.15)
    raise TelnetError(f"timed out waiting for game description prompt from {telnet.host}:{telnet.port}")


def return_to_server_menu_from_descriptions(telnet: TelnetSession, *, timeout: float) -> None:
    for command in ("Q", "?", ""):
        exit_start = len(telnet.text)
        telnet.send_line(command)
        try:
            wait_for_server_menu(telnet, since=exit_start, timeout=timeout, reject_description_menu=True)
            return
        except TelnetError:
            continue
    raise TelnetError(f"timed out returning to server menu from game descriptions on {telnet.host}:{telnet.port}")


def recover_to_menu(telnet: TelnetSession) -> None:
    for command in ("X", "Q", ""):
        start = len(telnet.text)
        telnet.send_line(command)
        try:
            wait_for_server_menu(telnet, since=start, timeout=8.0)
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
