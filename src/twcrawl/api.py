from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs

from .parser import clean_menu_game_name


def api_response(data: dict, path: str, query: str = "") -> tuple[int, dict]:
    parts = [part for part in path.strip("/").split("/") if part]
    params = parse_qs(query, keep_blank_values=True)
    if parts == ["api"]:
        return 200, api_index(data)
    if parts == ["api", "health"]:
        return 200, {"ok": True, "generated_at": data.get("generated_at"), "server_count": len(data.get("servers") or [])}
    if parts == ["api", "data"]:
        return 200, data
    if parts == ["api", "servers"]:
        return 200, {"servers": [server_payload(server, full=full(params)) for server in filtered_servers(data, params)]}
    if len(parts) >= 3 and parts[0:2] == ["api", "servers"]:
        server = find_server(data, parts[2])
        if server is None:
            return 404, {"error": "server not found", "server": parts[2]}
        if len(parts) == 3:
            return 200, server_payload(server, full=True)
        if len(parts) == 4 and parts[3] == "games":
            return 200, {"server": server_identity(server), "games": [game_payload(server, game, full=full(params)) for game in filtered_games(server, params)]}
        if len(parts) == 5 and parts[3] == "games":
            game = find_game(server, parts[4])
            if game is None:
                return 404, {"error": "game not found", "server": parts[2], "game": parts[4]}
            return 200, game_payload(server, game, full=True)
    if parts == ["api", "games"]:
        return 200, {"games": all_games(data, params)}
    if parts == ["api", "configurations"]:
        return 200, {"configurations": all_configurations(data, params)}
    return 404, {"error": "not found", "path": path}


def write_static_api(data: dict, out_dir: Path) -> None:
    api_dir = out_dir / "api"
    if api_dir.exists():
        shutil.rmtree(api_dir)
    api_dir.mkdir(parents=True, exist_ok=True)

    write_json(api_dir / "index.json", api_index(data))
    write_json(api_dir / "health.json", api_response(data, "/api/health")[1])
    write_json(api_dir / "data.json", data)
    write_json(api_dir / "servers.json", api_response(data, "/api/servers")[1])
    write_json(api_dir / "games.json", api_response(data, "/api/games")[1])
    write_json(api_dir / "configurations.json", api_response(data, "/api/configurations")[1])

    servers_dir = api_dir / "servers"
    servers_dir.mkdir(parents=True, exist_ok=True)
    for server in data.get("servers") or []:
        server_key = server_api_key(server)
        server_dir = servers_dir / server_key
        server_dir.mkdir(parents=True, exist_ok=True)
        write_json(servers_dir / f"{server_key}.json", server_payload(server, full=True))
        write_json(server_dir / "index.json", server_payload(server, full=True))
        write_json(server_dir / "games.json", {"server": server_identity(server), "games": [game_payload(server, game, full=True) for game in filtered_games(server, {})]})
        games_dir = server_dir / "games"
        games_dir.mkdir(parents=True, exist_ok=True)
        for game in filtered_games(server, {}):
            letter = str(game.get("letter") or "game").lower()
            write_json(games_dir / f"{letter}.json", game_payload(server, game, full=True))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def server_api_key(server: dict) -> str:
    return str(server.get("server_id") or server.get("slug") or "server")


def api_index(data: dict) -> dict:
    return {
        "name": "twcrawl API",
        "generated_at": data.get("generated_at"),
        "endpoints": [
            "/api/index.json",
            "/api/health.json",
            "/api/data.json",
            "/api/servers.json",
            "/api/servers/{server_id}.json",
            "/api/servers/{server_id}/games.json",
            "/api/servers/{server_id}/games/{letter}.json",
            "/api/games.json",
            "/api/configurations.json",
            "/api/health",
            "/api/data",
            "/api/servers",
            "/api/servers/{server_id_or_slug}",
            "/api/servers/{server_id_or_slug}/games",
            "/api/servers/{server_id_or_slug}/games/{letter}",
            "/api/games",
            "/api/configurations",
        ],
        "query": {
            "full": "Use full=1 on list endpoints to include raw_stats and complete stats objects.",
            "status": "Filter servers or games by status, such as online or ok.",
            "server": "Filter /api/games or /api/configurations by server id, slug, or name substring.",
        },
        "server_count": len(data.get("servers") or []),
        "game_count": sum(len(server.get("games") or []) for server in data.get("servers") or []),
    }


def full(params: dict[str, list[str]]) -> bool:
    return first(params, "full").lower() in {"1", "true", "yes", "on"}


def first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or []
    return values[0] if values else ""


def filtered_servers(data: dict, params: dict[str, list[str]]) -> list[dict]:
    servers = list(data.get("servers") or [])
    status = first(params, "status").lower()
    if status:
        servers = [server for server in servers if str(server.get("status") or "").lower() == status]
    return servers


def filtered_games(server: dict, params: dict[str, list[str]]) -> list[dict]:
    games = list(server.get("games") or [])
    status = first(params, "status").lower()
    if status:
        games = [game for game in games if str(game.get("status") or "").lower() == status]
    else:
        games = [game for game in games if relevant_game(game)]
    return games


def relevant_game(game: dict) -> bool:
    return game.get("status") == "ok" or bool(game.get("stats")) or bool(game.get("raw_stats"))


def all_games(data: dict, params: dict[str, list[str]]) -> list[dict]:
    server_filter = first(params, "server")
    games = []
    for server in data.get("servers") or []:
        if server_filter and not server_matches(server, server_filter):
            continue
        for game in filtered_games(server, params):
            games.append(game_payload(server, game, full=full(params)))
    return games


def all_configurations(data: dict, params: dict[str, list[str]]) -> list[dict]:
    server_filter = first(params, "server")
    configurations = []
    for server in data.get("servers") or []:
        if server_filter and not server_matches(server, server_filter):
            continue
        for game in filtered_games(server, params):
            configurations.append(
                {
                    **server_identity(server),
                    "game_letter": game.get("letter"),
                    "game_name": game_name(game),
                    "game_status": game.get("status"),
                    "stats": game.get("stats") or {},
                    "raw_stats": game.get("raw_stats") or "",
                }
            )
    return configurations


def server_payload(server: dict, *, full: bool = False) -> dict:
    if full:
        return server
    keys = [
        "server_id",
        "slug",
        "name",
        "telnet",
        "status",
        "last_crawled_at",
        "last_bigbang",
        "tradewars_version",
        "game_count",
        "players",
        "registered_to",
        "supports_games",
        "nodes",
        "error",
    ]
    return {key: server.get(key) for key in keys if key in server}


def game_payload(server: dict, game: dict, *, full: bool = False) -> dict:
    payload = {
        **server_identity(server),
        "letter": game.get("letter"),
        "name": game_name(game),
        "status": game.get("status"),
        "bigbang": game.get("bigbang"),
        "days_open": game.get("days_open"),
        "type": game.get("type"),
        "version": game.get("version"),
        "emulation": game.get("emulation"),
        "time": game.get("time"),
        "turns": game.get("turns"),
        "sectors": game.get("sectors"),
        "players": game.get("players"),
        "latency": (game.get("stats") or {}).get("Latency"),
        "ship_delay": (game.get("stats") or {}).get("Ship Delay"),
    }
    if full:
        if game_name(game) != str(game.get("name") or ""):
            payload["raw_name"] = game.get("name")
        payload["stats"] = game.get("stats") or {}
        payload["raw_stats"] = game.get("raw_stats") or ""
        payload["game"] = game
    return payload


def game_name(game: dict) -> str:
    raw_name = str(game.get("name") or "")
    return clean_menu_game_name(raw_name) or raw_name


def server_identity(server: dict) -> dict:
    return {
        "server_id": server.get("server_id"),
        "server_slug": server.get("slug"),
        "server_name": server.get("name"),
        "server_telnet": server.get("telnet"),
        "server_status": server.get("status"),
    }


def find_server(data: dict, value: str) -> dict | None:
    for server in data.get("servers") or []:
        if server_matches(server, value):
            return server
    return None


def server_matches(server: dict, value: str) -> bool:
    needle = value.casefold()
    return (
        needle == str(server.get("server_id", "")).casefold()
        or needle == str(server.get("slug", "")).casefold()
        or needle == str(server.get("name", "")).casefold()
        or needle in str(server.get("name", "")).casefold()
    )


def find_game(server: dict, letter: str) -> dict | None:
    target = letter.casefold()
    for game in server.get("games") or []:
        if str(game.get("letter", "")).casefold() == target:
            return game
    return None
