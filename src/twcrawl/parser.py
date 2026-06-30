from __future__ import annotations

import calendar
import re
from datetime import datetime


ANGLE_MENU_GAME_RE = re.compile(r"<([A-Z])>\s*([^<\n\r]*?)(?=<[A-Z#!]|\s+<[A-Z#!]|\n|$)")
DOT_MENU_GAME_RE = re.compile(r"(?:^|\s)([A-Z])\.\s+([^<\n\r]*?)(?=[A-Z]\.\s+|\s+[A-Z]\.\s+|\n|$)", re.MULTILINE)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LINE_ART_RE = re.compile(r"[╔╗╚╝╠╣╦╩╬═║▐▌▄▀█▓▒░■□▪▬▔▁▂▃▅▆▇·].*")


def parse_server_menu(text: str) -> dict:
    info: dict = {}
    version = re.search(r"TWGS\s+v?([0-9][^\s]*)", text, re.IGNORECASE)
    if version:
        info["tradewars_version"] = f"TWGS {version.group(1)}"
    registered = re.search(r"Server registered to\s+(.+)", text, re.IGNORECASE)
    if registered:
        info["registered_to"] = registered.group(1).strip()
    supports = re.search(r"Supports up to\s+(\d+)\s+games\s+and\s+(\d+)\s+nodes", text, re.IGNORECASE)
    if supports:
        info["supports_games"] = int(supports.group(1))
        info["nodes"] = int(supports.group(2))

    games = []
    seen: set[str] = set()
    for match in ANGLE_MENU_GAME_RE.finditer(text):
        add_menu_game(games, seen, match.group(1), match.group(2))
    for match in DOT_MENU_GAME_RE.finditer(text):
        add_menu_game(games, seen, match.group(1), match.group(2))
    info["menu_games"] = games
    return info


def add_menu_game(games: list[dict], seen: set[str], letter: str, raw_name: str) -> None:
    letter = letter.upper()
    if letter == "Q":
        return
    if letter in seen:
        return
    name = clean_menu_game_name(raw_name)
    if not name or name.lower() in {"quit", "players online", "view game descriptions", "description menu"}:
        return
    seen.add(letter)
    games.append({"letter": letter, "name": name})


def clean_menu_game_name(value: str) -> str:
    value = ANSI_RE.sub("", value)
    value = LINE_ART_RE.sub("", value)
    value = value.strip()
    value = re.split(r"\s{2,}", value, maxsplit=1)[0]
    value = re.sub(r"\s+\[[^\]]+\]\s*$", "", value)
    value = value.rstrip(" ·")
    return " ".join(value.split())


def parse_game_stats(text: str, crawl_time: datetime) -> dict:
    block = extract_stats_block(text)
    values = parse_key_values(block)
    local_game_year = game_year(values.get("Local Game Time"))
    result = {"raw_stats": block, "stats": values}

    result["bigbang"] = normalize_game_date(values.get("Start Day"), local_game_year, crawl_time)
    result["days_open"] = int_value(values.get("Game Age"))
    result["type"] = "Closed" if truthy(values.get("Closed Game")) else "Open"
    result["version"] = format_game_version(values)
    result["emulation"] = short_bandwidth(values.get("Input Bandwidth") or values.get("Output Bandwidth"))
    result["time"] = values.get("Time Online", "")
    result["turns"] = values.get("Turn Base", "")
    result["sectors"] = int_value(values.get("Sectors"))
    result["players"] = int_value(values.get("Active Players"))
    return result


def extract_stats_block(text: str) -> str:
    start = text.find("Game Stats:")
    end = text.find("End Stats.", start)
    if start == -1:
        return text.strip()
    if end == -1:
        return text[start:].strip()
    return text[start : end + len("End Stats.")].strip()


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line in {"Game Stats:", "End Stats."}:
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def format_game_version(values: dict[str, str]) -> str:
    major = values.get("Major Version", "")
    minor = values.get("Minor Version", "")
    if major and minor:
        version = f"{major}.{minor}"
    else:
        version = ""
    if truthy(values.get("Gold Enabled")):
        version += "G"
    if truthy(values.get("MBBS Compatibility")):
        version += "M"
    return version


def short_bandwidth(value: str | None) -> str:
    if not value:
        return ""
    return value.replace(" Broadband", "").strip()


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "yes", "1", "on"}


def int_value(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"-?\d[\d,]*", value)
    if not match:
        return None
    return int(match.group(0).replace(",", ""))


def game_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b\d{1,2}/\d{1,2}/(\d{2})\b", value)
    return int(match.group(1)) if match else None


def normalize_game_date(value: str | None, local_game_year: int | None, crawl_time: datetime) -> str:
    if not value:
        return ""
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b", value)
    if not match:
        return value
    month, day, yy = map(int, match.groups())
    if local_game_year is None:
        year = 2000 + yy
    else:
        year = crawl_time.year + (yy - local_game_year)
    if month < 1 or month > 12:
        return value
    day = min(day, calendar.monthrange(year, month)[1])
    return f"{month:02d}/{day:02d}/{year:04d}"
