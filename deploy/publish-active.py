"""Publish only the API-driven activity page, preserving crawler data and indexes."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def publish(source: Path, document_root: Path) -> list[Path]:
    web = source / "src" / "twcrawl" / "web"
    names = ("active.html", "twcrawl-active.css", "twcrawl-active.js")
    for name in names:
        if not (web / name).is_file():
            raise FileNotFoundError(web / name)
    if not (document_root / "games" / "style.css").is_file():
        raise FileNotFoundError("Expected the existing /games/style.css under the document root")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = source / "data" / "logs" / f"active-backup-{stamp}"
    result = []
    for name in names:
        relative = Path(name) if name.endswith(".html") else Path("assets") / name
        target = document_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(web / name, temporary)
        temporary.chmod(0o644)
        temporary.replace(target)
        result.append(target)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-root", type=Path, required=True)
    args = parser.parse_args()
    for path in publish(Path(__file__).resolve().parents[1], args.document_root):
        print(f"Published {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
