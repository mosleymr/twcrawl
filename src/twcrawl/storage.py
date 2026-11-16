from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .parser import game_year, int_value, normalize_game_date


def timestamp(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value or "")
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def calendar_date(value: str | None) -> date | None:
    for pattern in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(str(value or "").strip(), pattern).date()
        except ValueError:
            pass
    return None


def captured_at(server: dict, data: dict) -> datetime | None:
    return timestamp(server.get("last_success_at") or server.get("last_crawled_at") or data.get("generated_at"))


def normalize_snapshot_dates(data: dict) -> dict:
    servers = []
    for server in data.get("servers", []):
        captured = captured_at(server, data)
        games = []
        for game in server.get("games", []):
            stats = game.get("stats") or {}
            value = game.get("bigbang")
            if captured and stats.get("Start Day"):
                value = normalize_game_date(stats["Start Day"], game_year(stats.get("Local Game Time")), captured,
                                            game_age=int_value(stats.get("Game Age")))
            parsed = calendar_date(value)
            games.append({**game, "bigbang": parsed.strftime("%m/%d/%Y") if parsed else value or ""})
        dates = [parsed for game in games if (parsed := calendar_date(game.get("bigbang")))]
        servers.append({**server, "games": games,
                        "last_bigbang": max(dates).strftime("%m/%d/%Y") if dates else server.get("last_bigbang", "")})
    return {**data, "servers": servers}


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
    data = normalize_snapshot_dates(data)
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
            if str(row.get("player") or "").strip().casefold() == str(server.get("bot_name") or "twcrawl").strip().casefold():
                continue
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

    previous = normalize_snapshot_dates(previous) if previous else {}
    current = normalize_snapshot_dates(current)
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
        old_date, new_date = calendar_date(old_game.get("bigbang")), calendar_date(game.get("bigbang"))
        if bool(old_date) != bool(new_date):
            continue
        if old_date and new_date and old_date != new_date:
            before, after = captured_at(old[0], previous), captured_at(server, current)
            # An older corrected date or a shifted/future year is not a reset.
            # Allow one calendar day for the game server's timezone.
            if (new_date > old_date and before and after and after > before
                    and before.date() - timedelta(days=1) <= new_date <= after.date() + timedelta(days=1)):
                rebanged.append({**identity(server, game), "previous_bigbang": old_game.get("bigbang")})
            # Different game epochs cannot establish newly joined players.
            continue
        if (game.get("high_scores_error") or not game.get("high_scores_checked_at")
                or game.get("high_scores_checked_at") == old_game.get("high_scores_checked_at")):
            continue
        # An unavailable previous roster is a baseline, not evidence of new joins.
        if "high_scores" not in old_game or old_game.get("high_scores_error"):
            continue
        names = {p.get("name", "").strip().casefold() for p in old_game.get("high_scores", [])}
        for player in game.get("high_scores", []):
            if player.get("name", "").strip() and player["name"].strip().casefold() not in names:
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
        "baseline": not bool(previous.get("servers")), "comparison_version": 2,
        "new_games": new, "removed_games": removed,
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
