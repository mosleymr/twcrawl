"""Rebuild derived dates and comparisons without crawling or discarding history."""
from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .storage import atomic_json, compare_crawls, normalize_snapshot_dates


def repair_reports(database: Path, data_path: Path, *, apply: bool = False) -> dict:
    if not database.exists():
        raise ValueError(f"archive does not exist: {database}")
    changes = []
    backup = None
    uri = f"{database.resolve().as_uri()}?mode={'rw' if apply else 'ro'}"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        rows = connection.execute("SELECT id, data, report FROM runs ORDER BY id").fetchall()
        previous = None
        latest = None
        dates_changed = 0
        for run_id, raw, old_report in rows:
            original = json.loads(raw)
            data = normalize_snapshot_dates(original)
            dates_changed += sum(
                game.get("bigbang") != old.get("bigbang")
                for server, before in zip(data.get("servers", []), original.get("servers", []))
                for game, old in zip(server.get("games", []), before.get("games", []))
            )
            report = {**compare_crawls(previous, data), "run_id": run_id}
            data = {**data, "latest_report": report, "run_id": run_id}
            if data != original or report != json.loads(old_report):
                changes.append((json.dumps(data), json.dumps(report), run_id))
            previous, latest = data, data

        updated_json = None
        if data_path.exists():
            original_json = json.loads(data_path.read_text(encoding="utf-8"))
            updated_json = normalize_snapshot_dates(original_json)
            # A newer local edit must not be replaced by the archived snapshot.
            if (latest and original_json.get("run_id") == latest["run_id"]
                    and original_json.get("generated_at") == latest.get("generated_at")):
                updated_json["latest_report"] = latest["latest_report"]
            if updated_json == original_json:
                updated_json = None

        if apply and (changes or updated_json is not None):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = database.parent / "logs" / f"report-repair-{stamp}"
            backup.mkdir(parents=True)
            # A separate reader can back up the pre-repair state while this
            # transaction holds the writer lock, including committed WAL data.
            with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as reader, \
                    closing(sqlite3.connect(backup / database.name)) as target:
                reader.backup(target)
            if data_path.exists():
                shutil.copy2(data_path, backup / "crawl-data.json")
            connection.executemany("UPDATE runs SET data = ?, report = ? WHERE id = ?", changes)
    if apply and updated_json is not None:
        atomic_json(data_path, updated_json)
    return {
        "applied": apply, "runs_checked": len(rows), "runs_changed": len(changes),
        "game_dates_corrected": dates_changed, "json_changed": updated_json is not None,
        "backup": str(backup) if backup else None,
        "latest_run_id": latest.get("run_id") if latest else None,
        "latest_rebangs": len(latest["latest_report"]["rebanged_games"]) if latest else 0,
    }
