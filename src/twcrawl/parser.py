from __future__ import annotations

import calendar
import re
import xml.etree.ElementTree as ET
from datetime import datetime


ANGLE_MENU_GAME_RE = re.compile(r"<([A-Z])>\s*([^<\n\r]*?)(?=<[A-Z#!]|\s+<[A-Z#!]|\n|$)")
DOT_MENU_GAME_RE = re.compile(r"(?:^|\s)([A-Z])\.\s+([^<\n\r]*?)(?=[A-Z]\.\s+|\s+[A-Z]\.\s+|\n|$)", re.MULTILINE)
DESCRIPTION_TITLE_RE = re.compile(r"^[ \t]*([A-Z])[ \t]{2,}(.+?)[ \t]*$", re.MULTILINE)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LINE_ART_RE = re.compile(r"[╔╗╚╝╠╣╦╩╬═║▐▌▄▀█▓▒░■□▪▬▔▁▂▃▅▆▇·].*")
DESCRIPTION_ART_RE = re.compile(r"^[\\/_|\- ._=`~^]+$")
TWGS_XML_END = "</TWGSData>"

XML_STAT_KEYS = {
    "GoldEnabled": "Gold Enabled",
    "MBBSCompatibility": "MBBS Compatibility",
    "StartDay": "Start Day",
    "GameAge": "Game Age",
    "LastExternDay": "Last Extern Day",
    "InternalAliens": "Internal Aliens",
    "InternalFerrengi": "Internal Ferrengi",
    "ClosedGame": "Closed Game",
    "ShowStardock": "Show Stardock",
    "TurnBase": "Turn Base",
    "TimeOnline": "Time Online",
    "InactiveTime": "Inactive Time",
    "LastBustClearDay": "Last Bust Clear Day",
    "InitialFighters": "Initial Fighters",
    "InitialCredits": "Initial Credits",
    "InitialHolds": "Initial Holds",
    "NewPlayerPlanets": "New Player Planets",
    "DaysTilDeletion": "Days Til Deletion",
    "ColonistRegenRate": "Colonist Regen Rate",
    "MaxPlanetSector": "Max Planet Sector",
    "MaxCorpMembers": "Max Corp Members",
    "FedSpaceShipLimit": "FedSpace Ship Limit",
    "PhotonMissileDuration": "Photon Missile Duration",
    "FedSpacePhotons": "FedSpace Photons",
    "PhotonsDisablePlayers": "Photons Disable Players",
    "CloakFailPercent": "Cloak Fail Percent",
    "DebrisLossPercent": "Debris Loss Percent",
    "TradePercent": "Trade Percent",
    "StealBuy": "Steal Buy",
    "ProductionRate": "Production Rate",
    "MaxProductionRegen": "Max Production Regen",
    "MultiplePhotons": "Multiple Photons",
    "ClearBustDays": "Clear Bust Days",
    "StealFactor": "Steal Factor",
    "RobFactor": "Rob Factor",
    "PortProductionMax": "Port Production Max",
    "RadiationLifetime": "Radiation Lifetime",
    "FighterLockDecay": "Fighter Lock Decay",
    "InvincibleFerengal": "Invincible Ferengal",
    "MBBSCombat": "MBBS Combat",
    "DeathDelay": "Death Delay",
    "DeathsPerDay": "Deaths Per Day",
    "StartupAssetDropoff": "Startup Asset Dropoff",
    "ShowWhosOnline": "Show Whos Online",
    "InteractiveSub-prompts": "Interactive Sub-prompts",
    "AllowAliases": "Allow Aliases",
    "AlienSleepMode": "Alien Sleep Mode",
    "AllowMBBSMegaRobBug": "Allow MBBS MegaRob Bug",
    "MaxTerraColonists": "Max Terra Colonists",
    "MinimumLoginTime": "Minimum Login Time",
    "TurnAccumulationDays": "Turn Accumulation Days",
    "PodlessCaptures": "Podless Captures",
    "CaptureFailPercent": "Capture Fail Percent",
    "MaxBankCredits": "Max Bank Credits",
    "HighScoreMode": "High Score Mode",
    "HighScoreType": "High Score Type",
    "RankingsMode": "Rankings Mode",
    "RankingsType": "Rankings Type",
    "EntryLogBlackout": "Entry Log Blackout",
    "GameLogBlackout": "Game Log Blackout",
    "PortReportDelay": "Port Report Delay",
    "InputBandwidth": "Input Bandwidth",
    "OutputBandwidth": "Output Bandwidth",
    "Latency": "Latency",
    "ShipDelay": "Ship Delay",
    "PlanetDelay": "Planet Delay",
    "OtherAttacksDelay": "Other Attacks Delay",
    "EProbeDelay": "EProbe Delay",
    "CrimeDelay": "Crime Delay",
    "PhotonLaunchDelay": "Photon Launch Delay",
    "PhotonWaveDelay": "Photon Wave Delay",
    "GenesisLaunchDelay": "Genesis Launch Delay",
    "ICPowerupDelay": "IC Powerup Delay",
    "PIGPowerupDelay": "PIG Powerup Delay",
    "PlanetLandingTakeoffDelay": "Planet Landing/Takeoff Delay",
    "PortDockDepartDelay": "Port Dock/Depart Delay",
    "ShipTransporterDelay": "Ship Transporter Delay",
    "PlanetTransporterDelay": "Planet Transporter Delay",
    "TakeDropFightersDelay": "Take/Drop Fighters Delay",
    "DropTakeMinesDelay": "Drop/Take Mines Delay",
    "TavernAnnouncement": "Tavern Announcement",
    "LimpetRemoval": "Limpet Removal",
    "ReregisterShip": "Reregister Ship",
    "CitadelTransportUnit": "Citadel Transport Unit",
    "CitadelTransportUpgrade": "Citadel Transport Upgrade",
    "GenesisTorpedo": "Genesis Torpedo",
    "ArmidMine": "Armid Mine",
    "LimpetMine": "Limpet Mine",
    "TypeITWarp": "Type I TWarp",
    "TypeIITWarp": "Type II TWarp",
    "TWarpUpgrade": "TWarp Upgrade",
    "PsychicProbe": "Psychic Probe",
    "PlanetScanner": "Planet Scanner",
    "AtomicDetonator": "Atomic Detonator",
    "EtherProbe": "Ether Probe",
    "PhotonMissile": "Photon Missile",
    "CloakingDevice": "Cloaking Device",
    "MineDisruptor": "Mine Disruptor",
    "HolographicScanner": "Holographic Scanner",
    "DensityScanner": "Density Scanner",
    "Sectors": "Sectors",
    "Users": "Users",
    "Aliens": "Aliens",
    "Ships": "Ships",
    "Ports": "Ports",
    "Planets": "Planets",
    "MaxCourseLength": "Max Course Length",
    "TournamentMode": "Tournament Mode",
    "DaysToEnter": "Days To Enter",
    "LockoutMode": "Lockout Mode",
    "MaxTimesBlownUp": "Max Times Blown Up",
    "ActivePlayers": "Active Players",
    "PercentPlayersGood": "Percent Players Good",
    "ActiveAliens": "Active Aliens",
    "PercentAliensGood": "Percent Aliens Good",
    "ActivePorts": "Active Ports",
    "PortValue": "Port Value",
    "ActivePlanets": "Active Planets",
    "PercentPlanetCitadels": "Percent Planet Citadels",
    "ActiveShips": "Active Ships",
    "ActiveCorps": "Active Corps",
    "ActiveFigs": "Active Figs",
    "ActiveMines": "Active Mines",
    "LocalGameTime": "Local Game Time",
}


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


def parse_twgs_xml(text: str, crawl_time: datetime) -> dict:
    xml = extract_twgs_xml(text)
    if not xml:
        return {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    server_node = root.find("Server")
    server_info = parse_xml_server(server_node)
    game_version = {
        "Major Version": child_text(server_node, "GameMajorVersion"),
        "Minor Version": child_text(server_node, "GameMinorVersion"),
    }
    server_game_year = game_year(child_text(server_node, "ServerLocalTime"))

    games = []
    for game_node in root.findall("./Games/Game"):
        parsed = parse_xml_game(game_node, crawl_time, game_version, server_game_year)
        if parsed:
            games.append(parsed)
    server_info["xml_games"] = games
    server_info["twgs_xml"] = {
        "game_count": len(games),
    }
    return server_info


def extract_twgs_xml(text: str) -> str:
    start = text.find("<TWGSData>")
    end = text.find(TWGS_XML_END, start)
    if start == -1 or end == -1:
        return ""
    return text[start : end + len(TWGS_XML_END)]


def parse_xml_server(server_node: ET.Element | None) -> dict:
    if server_node is None:
        return {}
    info: dict = {}
    host = child_text(server_node, "Host")
    if host:
        info["registered_to"] = host
    slots = int_value(child_text(server_node, "Slots"))
    if slots is not None:
        info["supports_games"] = slots
    nodes = int_value(child_text(server_node, "Nodes"))
    if nodes is not None:
        info["nodes"] = nodes
    major = child_text(server_node, "ServerMajorVersion")
    minor = child_text(server_node, "ServerMinorVersion")
    if major and minor:
        info["tradewars_version"] = f"TWGS {major}.{minor}"
    info["server_local_time"] = child_text(server_node, "ServerLocalTime")
    info["server_local_time_zone"] = child_text(server_node, "ServerLocalTimeZone")
    return {key: value for key, value in info.items() if value not in {None, ""}}


def parse_xml_game(
    game_node: ET.Element,
    crawl_time: datetime,
    game_version: dict[str, str],
    server_game_year: int | None,
) -> dict:
    letter = child_text(game_node, "./ID/GameSlot").upper()
    name = child_text(game_node, "./ID/GameName")
    if not letter or not name:
        return {}

    stats = xml_game_stats(game_node)
    for key, value in game_version.items():
        if value:
            stats.setdefault(key, value)
    local_game_year = game_year(stats.get("Local Game Time")) or server_game_year

    result: dict = {
        "letter": letter,
        "name": name,
        "name_source": "twgs_xml",
        "status": "xml",
        "stats": stats,
        "xml": xml_game_sections(game_node),
        "raw_xml": ET.tostring(game_node, encoding="unicode"),
    }
    result["bigbang"] = normalize_game_date(stats.get("Start Day"), local_game_year, crawl_time)
    result["days_open"] = int_value(stats.get("Game Age"))
    result["type"] = "Closed" if truthy(stats.get("Closed Game")) else "Open"
    result["version"] = format_game_version(stats)
    result["emulation"] = short_bandwidth(stats.get("Input Bandwidth") or stats.get("Output Bandwidth"))
    result["time"] = stats.get("Time Online", "")
    result["turns"] = stats.get("Turn Base", "")
    result["sectors"] = int_value(stats.get("Sectors"))
    result["players"] = int_value(stats.get("Active Players"))
    return result


def xml_game_stats(game_node: ET.Element) -> dict[str, str]:
    stats: dict[str, str] = {}
    for node in game_node.iter():
        if node is game_node or list(node):
            continue
        text = (node.text or "").strip()
        if not text:
            continue
        key = XML_STAT_KEYS.get(node.tag)
        if key:
            stats[key] = text
    return stats


def xml_game_sections(game_node: ET.Element) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    for section in list(game_node):
        values = xml_section_values(section)
        if values:
            sections[section.tag] = values
    return sections


def xml_section_values(node: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in node.iter():
        if child is node or list(child):
            continue
        text = (child.text or "").strip()
        if text:
            values[child.tag] = text
    return values


def child_text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    child = node.find(path)
    return (child.text or "").strip() if child is not None and child.text else ""


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
