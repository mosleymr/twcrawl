from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from .crawler import slugify


DEFAULT_ARCHIVE_URL = "https://web.archive.org/web/20260513011549id_/https://www.microblaster.net/servers.aspx"


def import_microblaster(url: str = DEFAULT_ARCHIVE_URL) -> dict:
    source = urlopen(url, timeout=30).read().decode("utf-8", "replace")
    servers = []
    for row in re.findall(r"<tr[^>]*bgcolor=\"Transparent\"[^>]*>(.*?)</tr>", source, re.I | re.S):
        if "type=twgs2" not in row.lower():
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)
        if len(cells) < 7:
            continue
        detail = re.search(r"ServerDetail\.aspx\?type=twgs2&amp;serverid=(\d+)", row, re.I)
        telnet = re.search(r"href=\"Telnet://([^\"]+)\"", cells[0], re.I)
        name = strip(cells[1])
        if not (detail and telnet and name):
            continue
        server_id = detail.group(1)
        servers.append(
            {
                "server_id": server_id,
                "type": "twgs2",
                "name": name,
                "slug": slugify(name),
                "telnet": telnet.group(1),
                "last_bigbang": strip(cells[2]),
                "bbs": strip(cells[3]),
                "tradewars_version": strip(cells[4]),
                "game_count": as_int(strip(cells[5])),
                "players": as_int(strip(cells[6])),
                "status": "seed",
                "archived_detail_url": (
                    "https://web.archive.org/web/20260513011549/"
                    f"http://microblaster.net/ServerDetail.aspx?type=twgs2&serverid={server_id}"
                ),
            }
        )
    return {
        "source": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "servers": servers,
    }


def write_seed(path: Path, url: str = DEFAULT_ARCHIVE_URL) -> dict:
    data = import_microblaster(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def strip(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def as_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0

