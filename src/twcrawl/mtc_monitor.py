from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .api import game_payload
from .crawler import parse_telnet_address
from .online import fetch_players_online, match_online_game


DEFAULT_MTC_GAMES_DIR = Path("/Users/mosleym/twx/games")


def monitor_recent_mtc_games(
    data: dict,
    *,
    mtc_games_dir: Path = DEFAULT_MTC_GAMES_DIR,
    days: int = 60,
    state_path: Path,
    live: bool = True,
    bot_name: str = "twcrawl",
    connect_timeout: float = 12.0,
    menu_timeout: float = 20.0,
    save: bool = True,
) -> dict:
    previous = load_state(state_path)
    mtc_games = recent_mtc_games(mtc_games_dir, days=days)
    twcrawl_games = match_twcrawl_games(data, mtc_games)
    live_rows_by_server = {}
    live_errors_by_server = {}

    if live:
        for server_key, group in group_by_server(twcrawl_games).items():
            server = group["server"]
            try:
                rows, raw = fetch_players_online(
                    {
                        "server_name": server.get("name"),
                        "server_telnet": server.get("telnet"),
                    },
                    bot_name=bot_name,
                    connect_timeout=connect_timeout,
                    menu_timeout=menu_timeout,
                )
                live_rows_by_server[server_key] = {"rows": rows, "raw": raw}
            except Exception as exc:
                live_errors_by_server[server_key] = str(exc)

    results = []
    next_state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "games": {},
    }
    previous_games = previous.get("games") or {}

    for item in twcrawl_games:
        key = item["key"]
        server = item.get("server")
        game = item.get("game")
        current_players = player_rows(game) if game else []
        current_names = {player["name"].casefold() for player in current_players if player.get("name")}
        previous_names = {
            str(player.get("name") or "").casefold()
            for player in (previous_games.get(key) or {}).get("players", [])
            if player.get("name")
        }
        baseline = key not in previous_games
        new_players = [] if baseline else [player for player in current_players if player.get("name", "").casefold() not in previous_names]
        online_players = []
        live_error = ""
        if server and game and live:
            server_key = server_identity_key(server)
            live_error = live_errors_by_server.get(server_key, "")
            live_rows = (live_rows_by_server.get(server_key) or {}).get("rows") or []
            online_players = online_players_for_game(live_rows, server, game)

        result = {
            "key": key,
            "mtc": item["mtc"],
            "matched": bool(server and game),
            "baseline": baseline,
            "new_players": new_players,
            "online_players": online_players,
            "live_error": live_error,
        }
        if server:
            result["server"] = server_summary(server)
        if game:
            result["game"] = game_payload(server, game, full=False) if server else game
            result["players"] = current_players
        else:
            result["players"] = []
            result["match_error"] = item.get("error", "no matching crawled game")
        results.append(result)

        next_state["games"][key] = {
            "checked_at": next_state["generated_at"],
            "mtc": item["mtc"],
            "server": server_summary(server) if server else None,
            "game": game_payload(server, game, full=False) if server and game else None,
            "players": current_players,
        }

    report = {
        "generated_at": next_state["generated_at"],
        "days": days,
        "live": live,
        "mtc_games_dir": str(mtc_games_dir),
        "game_count": len(results),
        "matched_count": sum(1 for row in results if row["matched"]),
        "new_player_count": sum(len(row["new_players"]) for row in results),
        "online_player_count": sum(len(row["online_players"]) for row in results),
        "results": sorted(results, key=sort_monitor_result),
    }

    if save:
        write_state(state_path, next_state)
        write_last_report(state_path, report)
    return report


def recent_mtc_games(root: Path, *, days: int) -> list[dict]:
    cutoff = time.time() - (days * 86400)
    by_key: dict[str, dict] = {}
    for path in root.rglob("*.json"):
        if path.name == "variables.json" or path.name.endswith(".bak"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        host = str(data.get("Host") or "").strip()
        port = int_value(data.get("Port"))
        letter = str(data.get("GameLetter") or "").strip().upper()
        if not host or not port or len(letter) != 1 or not letter.isalpha():
            continue
        item = {
            "key": mtc_key(host, port, letter),
            "path": str(path),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "name": data.get("Name"),
            "host": host,
            "port": port,
            "telnet": f"{host}:{port}",
            "letter": letter,
            "login_name": data.get("LoginName"),
            "database_path": data.get("DatabasePath"),
        }
        existing = by_key.get(item["key"])
        if existing is None or item["modified_at"] > existing["modified_at"]:
            by_key[item["key"]] = item
    return sorted(by_key.values(), key=lambda item: item["modified_at"], reverse=True)


def match_twcrawl_games(data: dict, mtc_games: list[dict]) -> list[dict]:
    results = []
    servers = data.get("servers") or []
    for mtc in mtc_games:
        server = find_server_by_telnet(servers, mtc["host"], mtc["port"])
        if server is None:
            results.append({"key": mtc["key"], "mtc": mtc, "error": "server not found in twcrawl data"})
            continue
        game = find_game_by_letter(server, mtc["letter"])
        if game is None:
            results.append({"key": mtc["key"], "mtc": mtc, "server": server, "error": "game letter not found in twcrawl data"})
            continue
        results.append({"key": mtc["key"], "mtc": mtc, "server": server, "game": game})
    return results


def find_server_by_telnet(servers: list[dict], host: str, port: int) -> dict | None:
    target_host = host.casefold()
    for server in servers:
        try:
            server_host, server_port = parse_telnet_address(str(server.get("telnet") or ""))
        except Exception:
            continue
        if server_host.casefold() == target_host and server_port == port:
            return server
    return None


def find_game_by_letter(server: dict, letter: str) -> dict | None:
    target = letter.casefold()
    for game in server.get("games") or []:
        if str(game.get("letter") or "").casefold() == target:
            return game
    return None


def online_players_for_game(rows: list[dict], server: dict, game: dict) -> list[dict]:
    known_games = [candidate for candidate in server.get("games") or [] if candidate.get("status") == "ok"]
    result = []
    for row in rows:
        matched = match_online_game(row, known_games)
        if matched and str(matched.get("letter") or "").casefold() == str(game.get("letter") or "").casefold():
            result.append(row)
    return result


def group_by_server(items: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for item in items:
        server = item.get("server")
        if not server:
            continue
        key = server_identity_key(server)
        group = groups.setdefault(key, {"server": server, "items": []})
        group["items"].append(item)
    return groups


def player_rows(game: dict | None) -> list[dict]:
    if not game:
        return []
    rows = []
    for row in game.get("high_scores") or []:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "position": row.get("position"),
                "rank": row.get("rank"),
                "alignment": row.get("alignment"),
                "corp": row.get("corp"),
                "name": name,
                "ship_type": row.get("ship_type"),
            }
        )
    return rows


def format_monitor_report(report: dict) -> str:
    lines = [
        (
            f"{report['game_count']} recent MTC game(s); "
            f"{report['matched_count']} matched twcrawl game(s); "
            f"{report['new_player_count']} new player(s); "
            f"{report['online_player_count']} currently online player(s)."
        )
    ]
    for row in report["results"]:
        mtc = row["mtc"]
        game = row.get("game") or {}
        title = f"{mtc['telnet']} {mtc['letter']}"
        if game.get("name"):
            title += f" {game.get('name')}"
        title += f" [{mtc.get('name')}]"
        lines.append("")
        lines.append(title)
        if not row["matched"]:
            lines.append(f"  match failed: {row.get('match_error')}")
            continue
        if row["baseline"]:
            lines.append("  baseline created; future runs will report new players.")
        if row["new_players"]:
            lines.append("  new players: " + ", ".join(player["name"] for player in row["new_players"]))
        else:
            lines.append("  new players: none")
        if not report.get("live"):
            lines.append("  online now: live check skipped")
        elif row["live_error"]:
            lines.append(f"  live check failed: {row['live_error']}")
        elif row["online_players"]:
            lines.append(
                "  online now: "
                + ", ".join(f"{player['player']} ({player['location']}, node {player['node']})" for player in row["online_players"])
            )
        else:
            lines.append("  online now: none")
    return "\n".join(lines)


def dumps_monitor_report(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"games": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"games": {}}


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_last_report(state_path: Path, report: dict) -> None:
    report_path = state_path.with_name(state_path.stem + "-last-report.json")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def server_summary(server: dict | None) -> dict | None:
    if not server:
        return None
    return {
        "server_id": server.get("server_id"),
        "slug": server.get("slug"),
        "name": server.get("name"),
        "telnet": server.get("telnet"),
        "status": server.get("status"),
        "last_crawled_at": server.get("last_crawled_at"),
    }


def server_identity_key(server: dict) -> str:
    return str(server.get("server_id") or server.get("telnet") or server.get("name"))


def mtc_key(host: str, port: int, letter: str) -> str:
    return f"{host.casefold()}:{port}:{letter.upper()}"


def sort_monitor_result(row: dict) -> tuple[str, str]:
    mtc = row.get("mtc") or {}
    return (str(mtc.get("host") or "").casefold(), str(mtc.get("letter") or ""))


def int_value(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
