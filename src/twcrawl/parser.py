from __future__ import annotations

import calendar
import re
from datetime import datetime


ANGLE_MENU_GAME_RE = re.compile(r"<([A-Z])>\s*([^<\n\r]*?)(?=<[A-Z#!]|\s+<[A-Z#!]|\n|$)")
DOT_MENU_GAME_RE = re.compile(r"(?:^|\s)([A-Z])\.\s+([^<\n\r]*?)(?=[A-Z]\.\s+|\s+[A-Z]\.\s+|\n|$)", re.MULTILINE)
DESCRIPTION_TITLE_RE = re.compile(r"^[ \t]*([A-Z])[ \t]{2,}(.+?)[ \t]*$", re.MULTILINE)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LINE_ART_RE = re.compile(r"[╔╗╚╝╠╣╦╩╬═║▐▌▄▀█▓▒░■□▪▬▔▁▂▃▅▆▇·].*")
DESCRIPTION_ART_RE = re.compile(r"^[\\/_|\- ._=`~^]+$")


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


def parse_game_description_summary(text: str) -> dict[str, str]:
    info = parse_server_menu(text)
    return {
        game["letter"]: game["name"]
        for game in info.get("menu_games", [])
        if is_usable_description_name(game.get("name", ""))
    }


def parse_game_description_title(text: str, letter: str) -> str:
    letter = letter.upper()
    head = description_detail_head(text)
    if re.search(r"\bNo description\b", head, re.IGNORECASE):
        return ""
    for match in DESCRIPTION_TITLE_RE.finditer(head):
        if match.group(1).upper() == letter:
            title = clean_menu_game_name(match.group(2))
            if is_usable_description_name(title):
                return title
    for match in ANGLE_MENU_GAME_RE.finditer(head):
        if match.group(1).upper() == letter:
            title = clean_menu_game_name(match.group(2))
            if is_usable_description_name(title):
                return title
    return ""


def description_detail_head(text: str) -> str:
    end = len(text)
    for marker in (
        "Show Game Descriptions",
        "[ANY KEY]",
        "[Any key",
        "Describe which game",
        "Select game",
    ):
        position = text.find(marker)
        if position >= 0:
            end = min(end, position)
    return text[:end]


def is_usable_description_name(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered in {"no description", "no description...", "________"}:
        return False
    if lowered.startswith(
        (
            "show game descriptions",
            "select game",
            "describe which game",
            "visit our website",
        )
    ):
        return False
    if DESCRIPTION_ART_RE.fullmatch(value):
        return False
    return any(char.isalnum() for char in value)


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


def parse_high_scores(text: str) -> dict:
    block = extract_high_scores_block(text)
    return {"raw_high_scores": block, "high_scores": parse_high_score_rows(block)}


def extract_high_scores_block(text: str) -> str:
    rankings_start = text.find("Trade Wars 2002 Trader Rankings")
    ranking_start = text.rfind("Ranking Traders", 0, rankings_start if rankings_start >= 0 else len(text))
    if rankings_start == -1:
        return text.strip()
    start = ranking_start if ranking_start >= 0 else rankings_start
    end_candidates = [
        position
        for position in (
            text.find("[Pause]", rankings_start),
            text.find("==-- Trade Wars 2002 --==", rankings_start),
            text.find("Enter your choice:", rankings_start),
        )
        if position >= 0
    ]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip()


def parse_high_score_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    in_rows = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if re.match(r"\s*---\s+-{5,}\s+--\s+-{5,}\s+-{5,}", line):
            in_rows = True
            continue
        if not in_rows:
            continue
        if not line.strip():
            if rows:
                break
            continue
        if line.lstrip().startswith("["):
            break
        parsed = parse_high_score_row(line)
        if parsed:
            rows.append(parsed)
    return rows


def parse_high_score_row(line: str) -> dict | None:
    if not re.match(r"\s*\d+\s", line):
        return None
    padded = line.ljust(78)
    position = int_value(padded[0:4])
    values = re.findall(r"-?[\d,]+", padded[4:25])
    rank = values[0] if values else ""
    alignment = values[1] if len(values) > 1 else ""
    corp = padded[26:29].strip()
    name = padded[29:60].strip()
    ship_type = padded[60:].strip()
    if position is None or not name:
        return None
    return {
        "position": position,
        "rank": rank,
        "rank_value": int_value(rank),
        "alignment": alignment,
        "alignment_value": int_value(alignment),
        "corp": corp,
        "name": name,
        "ship_type": ship_type,
    }


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
