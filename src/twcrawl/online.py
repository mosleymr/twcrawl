from __future__ import annotations

import json
import re
import time

from .api import find_player
from .crawler import parse_telnet_address, wait_for_server_menu
from .parser import clean_menu_game_name
from .telnet import TelnetError, TelnetSession


PLAYERS_ONLINE_QUIET_SECONDS = 1.0


def check_player_online(
    data: dict,
    player_name: str,
    *,
    bot_name: str = "twcrawl",
    connect_timeout: float = 12.0,
    menu_timeout: float = 20.0,
) -> dict:
    player = find_player(data, player_name)
    if player is None:
        return {"player": {"name": player_name, "game_count": 0}, "servers": []}

    server_groups = group_player_games_by_server(player["games"])
    results = []
    for server in server_groups:
        print(f"check {player['name']} on {server['server_name']} {server['server_telnet']}")
        try:
            rows, raw = fetch_players_online(
                server,
                bot_name=bot_name,
                connect_timeout=connect_timeout,
                menu_timeout=menu_timeout,
            )
            results.append(compare_player_locations(player["name"], server, rows, raw))
        except Exception as exc:
            results.append(
                {
                    "server_id": server["server_id"],
                    "server_name": server["server_name"],
                    "server_telnet": server["server_telnet"],
                    "status": "error",
                    "error": str(exc),
                    "known_games": server["games"],
                    "logged_in_games": [],
                    "not_logged_in_games": server["games"],
                    "online_locations": [],
                }
            )
            print(f"  error: {exc}")

    return {"player": {key: player.get(key) for key in ("name", "slug", "game_count")}, "servers": results}


def group_player_games_by_server(games: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for game in games:
        key = str(game.get("server_id"))
        group = groups.get(key)
        if group is None:
            group = {
                "server_id": game.get("server_id"),
                "server_name": game.get("server_name"),
                "server_slug": game.get("server_slug"),
                "server_telnet": game.get("server_telnet"),
                "games": [],
            }
            groups[key] = group
        group["games"].append(game)
    return sorted(groups.values(), key=lambda group: str(group.get("server_name") or "").casefold())


def fetch_players_online(
    server: dict,
    *,
    bot_name: str,
    connect_timeout: float,
    menu_timeout: float,
) -> tuple[list[dict], str]:
    host, port = parse_telnet_address(str(server["server_telnet"]))
    with TelnetSession(host, port, connect_timeout=connect_timeout) as telnet:
        telnet.wait_for("Please enter your name", timeout=connect_timeout)
        telnet.send_line(bot_name)
        menu_start = len(telnet.text)
        wait_for_server_menu(telnet, since=menu_start, timeout=menu_timeout)

        players_start = len(telnet.text)
        telnet.send_line("#")
        raw = wait_for_players_online(telnet, since=players_start, timeout=menu_timeout)
        try:
            telnet.send_line("Q")
        except Exception:
            pass
    return parse_players_online(raw), raw


def wait_for_players_online(telnet: TelnetSession, *, since: int, timeout: float) -> str:
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
        pause_at = window.rfind("[Pause]")
        if pause_at >= 0 and pause_at != pause_ack_at:
            pause_ack_at = pause_at
            telnet.send_line()
        if "Players Online" in window and time.monotonic() - last_change >= PLAYERS_ONLINE_QUIET_SECONDS:
            return window
        telnet.read_available(0.15)
    window = telnet.text[since:]
    if "Players Online" in window:
        return window
    raise TelnetError(f"timed out waiting for players online from {telnet.host}:{telnet.port}")


def parse_players_online(text: str) -> list[dict]:
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"\s*Node\s+(\d+)\s+(.+?)\s*:\s*(.*?)\s*$", line, re.IGNORECASE)
        if not match:
            continue
        player = " ".join(match.group(3).split())
        if not player:
            continue
        rows.append(
            {
                "node": int(match.group(1)),
                "location": " ".join(match.group(2).split()),
                "player": player,
            }
        )
    return rows


def compare_player_locations(player_name: str, server: dict, rows: list[dict], raw: str) -> dict:
    player_rows = [row for row in rows if row["player"].casefold() == player_name.casefold()]
    known_games = server["games"]
    logged_in_games = []
    unmatched_locations = []

    for row in player_rows:
        matched = match_online_game(row, known_games)
        if matched:
            logged_in_games.append({**matched, "online": row})
        else:
            unmatched_locations.append(row)

    logged_keys = {str(game.get("letter") or "").casefold() for game in logged_in_games}
    not_logged_in_games = [
        game for game in known_games if str(game.get("letter") or "").casefold() not in logged_keys
    ]
    status = "online" if player_rows else "not_online"
    if unmatched_locations and not logged_in_games:
        status = "online_unknown_location"
    elif unmatched_locations:
        status = "online_partial"

    return {
        "server_id": server["server_id"],
        "server_name": server["server_name"],
        "server_telnet": server["server_telnet"],
        "status": status,
        "known_games": known_games,
        "logged_in_games": logged_in_games,
        "not_logged_in_games": not_logged_in_games,
        "online_locations": player_rows,
        "unmatched_locations": unmatched_locations,
        "raw_players_online": raw,
    }


def match_online_game(row: dict, games: list[dict]) -> dict | None:
    location = normalize_location(row.get("location"))
    if not location or location == "menu":
        return None
    letter = infer_game_letter(location)
    if letter:
        for game in games:
            if str(game.get("letter") or "").casefold() == letter.casefold():
                return game
    for game in games:
        game_name = normalize_location(game.get("name"))
        if game_name and (game_name == location or game_name in location or location in game_name):
            return game
    return None


def infer_game_letter(location: str) -> str:
    match = re.search(r"(?:^|\b)game\s+([a-z])(?:\b|$)", location, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"<([a-z])>", location, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def normalize_location(value: object) -> str:
    return clean_menu_game_name(str(value or "")).casefold()


def format_online_report(result: dict) -> str:
    lines = []
    player = result["player"]
    lines.append(f"{player.get('name')} known games: {player.get('game_count', 0)}")
    if not result["servers"]:
        lines.append("No known games for that player in the current data.")
        return "\n".join(lines)

    for server in result["servers"]:
        lines.append("")
        lines.append(f"{server['server_name']} ({server['server_telnet']})")
        if server["status"] == "error":
            lines.append(f"  check failed: {server.get('error')}")
            continue
        if server["logged_in_games"]:
            for game in server["logged_in_games"]:
                online = game.get("online") or {}
                lines.append(
                    f"  logged in: {game.get('letter')} {game.get('name')} "
                    f"(node {online.get('node')}, {online.get('location')})"
                )
        elif server["online_locations"]:
            for location in server["online_locations"]:
                lines.append(f"  online, location not mapped to a known game: node {location.get('node')} {location.get('location')}")
        else:
            lines.append("  not logged in to this server")

        if server["not_logged_in_games"]:
            not_online = ", ".join(
                f"{game.get('letter')} {game.get('name')}" for game in server["not_logged_in_games"]
            )
            lines.append(f"  not in: {not_online}")
    return "\n".join(lines)


def dumps_online_report(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
