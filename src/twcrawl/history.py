from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def snapshot_data(data: dict, history_dir: Path, *, label: str = "") -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{slug_label(label)}" if label else ""
    path = history_dir / f"{timestamp}{suffix}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    latest = history_dir / "latest.json"
    shutil.copyfile(path, latest)
    update_manifest(history_dir, path)
    return path


def update_manifest(history_dir: Path, snapshot_path: Path) -> None:
    manifest_path = history_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    else:
        manifest = {}
    snapshots = [
        entry
        for entry in manifest.get("snapshots", [])
        if entry.get("file") != snapshot_path.name
    ]
    snapshots.append(
        {
            "file": snapshot_path.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    snapshots.sort(key=lambda entry: entry.get("file", ""))
    manifest["snapshots"] = snapshots
    manifest["latest"] = snapshot_path.name
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def slug_label(value: str) -> str:
    result = []
    for char in value.lower():
        if char.isalnum():
            result.append(char)
        elif result and result[-1] != "-":
            result.append("-")
    return "".join(result).strip("-") or "snapshot"
