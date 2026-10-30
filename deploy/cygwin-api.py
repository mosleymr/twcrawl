"""Keep the loopback API running using an existing user's Cygwin cron."""
from __future__ import annotations

import argparse
import fcntl
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BEGIN = "# BEGIN twcrawl stored API"
END = "# END twcrawl stored API"


def healthy() -> bool:
    try:
        with urlopen("http://127.0.0.1:8008/api/health", timeout=3) as response:
            data = json.load(response)
            return data.get("ok") is True and data.get("storage") == "sqlite"
    except Exception:
        return False


def ensure_running() -> None:
    logs = ROOT / "data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "api-start.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if healthy():
            print("Stored API is healthy on 127.0.0.1:8008")
            return
        with (logs / "api.log").open("a") as output:
            process = subprocess.Popen(
                [sys.executable, "-u", "-m", "twcrawl", "serve", "--api-only"],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        for _ in range(20):
            if healthy():
                print(f"Started stored API, PID {process.pid}; logs: {logs / 'api.log'}")
                return
            if process.poll() is not None:
                raise SystemExit(f"API exited with {process.returncode}; inspect {logs / 'api.log'}")
            time.sleep(0.5)
        raise SystemExit(f"API did not become healthy; inspect {logs / 'api.log'}")


def install_cron() -> None:
    current = subprocess.run(["crontab", "-l"], text=True, capture_output=True)
    if current.returncode and "no crontab" not in current.stderr.lower():
        raise SystemExit(current.stderr)
    original = current.stdout
    if BEGIN in original:
        raise SystemExit("API cron block already exists; leaving the crontab unchanged")
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} --ensure"
    log = shlex.quote(str(ROOT / "data" / "logs" / "api-watchdog.log"))
    block = f"{BEGIN}\n@reboot {command} >> {log} 2>&1\n*/5 * * * * {command} >> {log} 2>&1\n{END}\n"
    backup = ROOT / "data" / "logs" / f"crontab-before-api-{datetime.now():%Y%m%d-%H%M%S}.txt"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(original, encoding="utf-8")
    subprocess.run(["crontab", "-"], input=original.rstrip() + "\n" + block, text=True, check=True)
    print(f"Added API startup and five-minute health watchdog to current user's cron. Backup: {backup}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensure", action="store_true")
    parser.add_argument("--install-cron", action="store_true")
    args = parser.parse_args()
    if sys.platform != "cygwin":
        parser.error("this deployment helper requires Cygwin; use Task Scheduler for native Windows Python")
    if args.ensure:
        ensure_running()
    if args.install_cron:
        install_cron()
