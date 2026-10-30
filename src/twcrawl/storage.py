from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def latest_run(database: Path) -> dict | None:
    if not database.exists():
        return None
    with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True, timeout=15)) as connection:
        row = connection.execute("SELECT id, data FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return {"id": row[0], "data": json.loads(row[1])} if row else None


def read_runs(database: Path, *, run_id: int | None = None, limit: int = 50, before: int | None = None) -> list[dict]:
    if not database.exists():
        return []
    with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True, timeout=15)) as connection:
        connection.row_factory = sqlite3.Row
        if run_id is not None:
            rows = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchall()
            return [{**dict(row), "data": json.loads(row["data"]), "report": json.loads(row["report"])} for row in rows]
        rows = connection.execute(
            "SELECT id, created_at, generated_at, kind FROM runs WHERE (? IS NULL OR id < ?) ORDER BY id DESC LIMIT ?",
            (before, before, max(1, min(limit, 200))),
        ).fetchall()
    return [dict(row) for row in rows]


def archive_data(data: dict, database: Path, *, kind: str = "crawl", baseline: dict | None = None) -> dict:
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=30)) as connection, connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, "
            "generated_at TEXT, kind TEXT NOT NULL, data TEXT NOT NULL, report TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT data FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        previous = json.loads(row[0]) if row else baseline
        report = compare_crawls(previous, data)
        now = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            "INSERT INTO runs (created_at, generated_at, kind, data, report) VALUES (?, ?, ?, '', '')",
            (now, data.get("generated_at"), kind),
        )
        report["run_id"] = cursor.lastrowid
        data = {**data, "latest_report": report, "run_id": cursor.lastrowid}
        connection.execute("UPDATE runs SET data = ?, report = ? WHERE id = ?", (
            json.dumps(data), json.dumps(report), cursor.lastrowid,
        ))
    return data


def identity(server: dict, game: dict | None = None) -> dict:
    result = {
        "server_id": server.get("server_id"), "server_name": server.get("name"),
        "server_telnet": server.get("telnet"),
    }
    if game:
        result.update(letter=game.get("letter"), game_name=game.get("name"), bigbang=game.get("bigbang"))
    return result


def stored_activity(data: dict) -> dict:
    sessions, checks = [], []
    for server in data.get("servers", []):
        check = server.get("online_check") or {}
        checks.append({**identity(server), **{k: check.get(k) for k in ("checked_at", "error")},
                       "status": check.get("status", "unknown")})
        if check.get("status") != "ok":
            continue
        for row in check.get("players", []):
            sessions.append({**identity(server), **row, "checked_at": check.get("checked_at")})
    return {
        "generated_at": data.get("generated_at"), "online_sessions": sessions, "server_checks": checks,
        "session_count": len(sessions),
        "player_count": len({row.get("player", "").casefold() for row in sessions if row.get("player")}),
    }


def compare_crawls(previous: dict | None, current: dict) -> dict:
    def game_map(data: dict) -> dict:
        return {(s.get("telnet", "").casefold(), g.get("letter", "").upper()): (s, g)
                for s in data.get("servers", []) for g in s.get("games", [])}

    previous = previous or {}
    old_games, new_games = game_map(previous), game_map(current)
    new, removed, rebanged, joined = [], [], [], []
    for key, (server, game) in new_games.items():
        if server.get("status") != "online":
            continue
        old = old_games.get(key)
        if not old:
            if previous:
                new.append(identity(server, game))
            continue
        old_game = old[1]
        if game.get("bigbang") and old_game.get("bigbang") and game["bigbang"] != old_game["bigbang"]:
            rebanged.append({**identity(server, game), "previous_bigbang": old_game.get("bigbang")})
            continue
        if not game.get("high_scores_checked_at") or game.get("high_scores_checked_at") == old_game.get("high_scores_checked_at"):
            continue
        # An unavailable previous roster is a baseline, not evidence of new joins.
        if "high_scores" not in old_game or old_game.get("high_scores_error"):
            continue
        names = {p.get("name", "").casefold() for p in old_game.get("high_scores", [])}
        for player in game.get("high_scores", []):
            if player.get("name", "").casefold() not in names:
                joined.append({**identity(server, game), "player": player})
    current_servers = {s.get("telnet", "").casefold(): s for s in current.get("servers", [])}
    for key in old_games.keys() - new_games.keys():
        server = current_servers.get(key[0], {})
        if server.get("status") == "online" and server.get("crawl_complete"):
            removed.append(identity(*old_games[key]))

    activity = stored_activity(current)
    def presences(data: dict) -> dict:
        return {(r.get("server_telnet", "").casefold(), r.get("letter"), r.get("player", "").casefold()): r
                for r in stored_activity(data)["online_sessions"]}

    before, after = presences(previous), presences(current)
    previous_servers = {s.get("telnet", "").casefold(): s for s in previous.get("servers", [])}
    checked = {s.get("telnet", "").casefold() for s in current.get("servers", [])
               if (s.get("online_check") or {}).get("status") == "ok"
               and (previous_servers.get(s.get("telnet", "").casefold(), {}).get("online_check") or {}).get("status") == "ok"
               and (s.get("online_check") or {}).get("checked_at") !=
               (previous_servers[s.get("telnet", "").casefold()].get("online_check") or {}).get("checked_at")}
    return {
        "generated_at": current.get("generated_at"), "previous_generated_at": previous.get("generated_at"),
        "baseline": not bool(previous), "new_games": new, "removed_games": removed,
        "rebanged_games": rebanged, "new_players": joined,
        "newly_online": [after[k] for k in sorted(after.keys() - before.keys(), key=str) if k[0] in checked and previous],
        "no_longer_online": [before[k] for k in sorted(before.keys() - after.keys(), key=str) if k[0] in checked],
        "activity": activity,
        "summary": {"server_count": len(current.get("servers", [])), "game_count": len(new_games),
                    "online_servers": sum(s.get("status") == "online" for s in current.get("servers", [])),
                    "new_player_records": len(joined), "online_sessions": activity["session_count"]},
        "failures": [{**identity(s), "error": s.get("error"), "last_success_at": s.get("last_success_at")}
                     for s in current.get("servers", []) if s.get("status") != "online"],
    }
