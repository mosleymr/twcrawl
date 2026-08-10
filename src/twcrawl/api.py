from __future__ import annotations

import json
import re
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
    if parts == ["api", "players"]:
        return 200, {"players": player_index(data)}
    if len(parts) >= 3 and parts[0:2] == ["api", "players"]:
        player = find_player(data, parts[2])
        if player is None:
            return 404, {"error": "player not found", "player": parts[2]}
        if len(parts) == 3:
            return 200, player
        if len(parts) == 4 and parts[3] == "games":
            return 200, {"player": player_identity(player), "games": player["games"]}
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
    write_json(api_dir / "players.json", api_response(data, "/api/players")[1])

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

    players_dir = api_dir / "players"
    players_dir.mkdir(parents=True, exist_ok=True)
    for player in players(data):
        slug = player["slug"]
        player_dir = players_dir / slug
        player_dir.mkdir(parents=True, exist_ok=True)
        write_json(players_dir / f"{slug}.json", player)
        write_json(player_dir / "index.json", player)
        write_json(player_dir / "games.json", {"player": player_identity(player), "games": player["games"]})


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
            "/api/players.json",
            "/api/players/{player_slug}.json",
            "/api/players/{player_slug}/games.json",
            "/api/health",
            "/api/data",
            "/api/servers",
            "/api/servers/{server_id_or_slug}",
            "/api/servers/{server_id_or_slug}/games",
            "/api/servers/{server_id_or_slug}/games/{letter}",
            "/api/games",
            "/api/configurations",
            "/api/players",
            "/api/players/{player_slug_or_name}",
            "/api/players/{player_slug_or_name}/games",
        ],
        "query": {
            "full": "Use full=1 on list endpoints to include raw_stats and complete stats objects.",
            "status": "Filter servers or games by status, such as online or ok.",
            "server": "Filter /api/games or /api/configurations by server id, slug, or name substring.",
            "player": "Filter /api/games or /api/configurations by active player name substring.",
        },
        "server_count": len(data.get("servers") or []),
        "game_count": len(all_games(data, {})),
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
    return (
        game.get("status") == "ok"
        or bool(game.get("stats"))
        or bool(game.get("raw_stats"))
        or bool(game.get("high_scores"))
        or bool(game.get("raw_high_scores"))
    )


def all_games(data: dict, params: dict[str, list[str]]) -> list[dict]:
    server_filter = first(params, "server")
    player_filter = first(params, "player")
    games = []
    for server in data.get("servers") or []:
        if server_filter and not server_matches(server, server_filter):
            continue
        for game in filtered_games(server, params):
            if player_filter and not game_has_player(game, player_filter):
                continue
            games.append(game_payload(server, game, full=full(params)))
    return games


def all_configurations(data: dict, params: dict[str, list[str]]) -> list[dict]:
    server_filter = first(params, "server")
    player_filter = first(params, "player")
    configurations = []
    for server in data.get("servers") or []:
        if server_filter and not server_matches(server, server_filter):
            continue
        for game in filtered_games(server, params):
            if player_filter and not game_has_player(game, player_filter):
                continue
            configurations.append(
                {
                    **server_identity(server),
                    "game_letter": game.get("letter"),
                    "game_name": game_name(game),
                    "game_status": game.get("status"),
                    "stats": game.get("stats") or {},
                    "raw_stats": game.get("raw_stats") or "",
                    "high_scores": game.get("high_scores") or [],
                    "raw_high_scores": game.get("raw_high_scores") or "",
                }
            )
    return configurations


def player_index(data: dict) -> list[dict]:
    return [
        {key: value for key, value in player.items() if key != "games"}
        for player in players(data)
    ]


def players(data: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    slugs: set[str] = set()
    for server in data.get("servers") or []:
        for game in filtered_games(server, {}):
            game_summary = game_payload(server, game, full=False)
            for score in game.get("high_scores") or []:
                name = str(score.get("name") or "").strip()
                if not name:
                    continue
                key = name.casefold()
                player = grouped.get(key)
                if player is None:
                    slug = unique_slug(name, slugs)
                    player = {
                        "name": name,
                        "slug": slug,
                        "game_count": 0,
                        "games": [],
                    }
                    grouped[key] = player
                    slugs.add(slug)
                player["games"].append(
                    {
                        **game_summary,
                        "player": player_score_payload(score),
                    }
                )
    result = sorted(grouped.values(), key=lambda player: player["name"].casefold())
    for player in result:
        player["game_count"] = len(player["games"])
    return result


def player_identity(player: dict) -> dict:
    return {
        "name": player.get("name"),
        "slug": player.get("slug"),
        "game_count": player.get("game_count"),
    }


def find_player(data: dict, value: str) -> dict | None:
    needle = value.casefold()
    for player in players(data):
        if needle == str(player.get("slug") or "").casefold() or needle == str(player.get("name") or "").casefold():
            return player
    return None


def game_has_player(game: dict, value: str) -> bool:
    needle = value.casefold()
    return any(needle in str(score.get("name") or "").casefold() for score in game.get("high_scores") or [])


def player_score_payload(score: dict) -> dict:
    return {
        "position": score.get("position"),
        "rank": score.get("rank"),
        "rank_value": score.get("rank_value"),
        "alignment": score.get("alignment"),
        "alignment_value": score.get("alignment_value"),
        "corp": score.get("corp"),
        "name": score.get("name"),
        "ship_type": score.get("ship_type"),
    }


def unique_slug(value: str, used: set[str]) -> str:
    base = slugify(value)
    slug = base
    index = 2
    while slug in used:
        slug = f"{base}-{index}"
        index += 1
    return slug


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "player"


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
        "high_score_count": len(game.get("high_scores") or []),
        "active_player_names": [row.get("name") for row in game.get("high_scores") or [] if row.get("name")],
    }
    if full:
        if game_name(game) != str(game.get("name") or ""):
            payload["raw_name"] = game.get("name")
        payload["stats"] = game.get("stats") or {}
        payload["raw_stats"] = game.get("raw_stats") or ""
        payload["high_scores"] = game.get("high_scores") or []
        payload["raw_high_scores"] = game.get("raw_high_scores") or ""
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
