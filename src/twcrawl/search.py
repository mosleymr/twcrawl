from __future__ import annotations

import json

from .api import all_games, game_has_player


def search_games(
    data: dict,
    *,
    query: str = "",
    player: str = "",
    server: str = "",
    status: str = "",
    limit: int | None = None,
) -> list[dict]:
    params: dict[str, list[str]] = {"full": ["1"]}
    if server:
        params["server"] = [server]
    if status:
        params["status"] = [status]
    if player:
        params["player"] = [player]

    rows = []
    for game in all_games(data, params):
        raw_game = game.get("game") or {}
        if query and not game_matches_query(game, query):
            continue
        if player and not game_has_player(raw_game, player):
            continue
        rows.append(game)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def game_matches_query(game: dict, query: str) -> bool:
    needle = query.casefold()
    raw_game = game.get("game") or {}
    stats = game.get("stats") or {}
    haystack = [
        game.get("server_id"),
        game.get("server_slug"),
        game.get("server_name"),
        game.get("server_telnet"),
        game.get("letter"),
        game.get("name"),
        game.get("raw_name"),
        raw_game.get("menu_name"),
        raw_game.get("name_source"),
        game.get("type"),
        game.get("version"),
        game.get("emulation"),
        game.get("time"),
        game.get("turns"),
        game.get("latency"),
        game.get("ship_delay"),
    ]
    for key, value in stats.items():
        haystack.append(key)
        haystack.append(value)
    return any(needle in str(value or "").casefold() for value in haystack)


def format_search_results(games: list[dict], *, player: str = "") -> str:
    if not games:
        return "No matching games found."
    lines = [f"{len(games)} matching game(s):"]
    for game in games:
        player_suffix = ""
        if player:
            matches = [
                score
                for score in game.get("high_scores") or []
                if player.casefold() in str(score.get("name") or "").casefold()
            ]
            if matches:
                match = matches[0]
                detail = ", ".join(
                    value
                    for value in (
                        f"rank {match.get('rank')}" if match.get("rank") else "",
                        f"align {match.get('alignment')}" if match.get("alignment") else "",
                        str(match.get("ship_type") or ""),
                    )
                    if value
                )
                player_suffix = f" [{match.get('name')}: {detail}]" if detail else f" [{match.get('name')}]"
        lines.append(
            f"{game.get('server_name')} {game.get('letter')} {game.get('name')} "
            f"players={game.get('players')} days={game.get('days_open')} "
            f"telnet={game.get('server_telnet')}{player_suffix}"
        )
    return "\n".join(lines)


def dumps_search_results(games: list[dict]) -> str:
    return json.dumps({"count": len(games), "games": games}, indent=2, sort_keys=True)
