from __future__ import annotations

import html
import re
import shutil
from datetime import datetime
from pathlib import Path

from .parser import clean_menu_game_name


ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = ROOT / "assets"


def build_site(data: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    copy_assets(out_dir)
    (out_dir / "style.css").write_text(STYLE, encoding="utf-8")
    (out_dir / "index.html").write_text(render_index(data), encoding="utf-8")
    for server in data.get("servers", []):
        filename = server_filename(server)
        (out_dir / filename).write_text(render_server(data, server), encoding="utf-8")
        games = display_games(server)
        server_dir = out_dir / game_directory(server)
        if server_dir.exists():
            for stale in server_dir.glob("game-*.html"):
                stale.unlink()
        if games:
            server_dir.mkdir(parents=True, exist_ok=True)
            for game in games:
                (out_dir / game_filename(server, game)).write_text(render_game(data, server, game), encoding="utf-8")


def copy_assets(out_dir: Path) -> None:
    if not ASSET_DIR.exists():
        return
    target = out_dir / "assets"
    target.mkdir(parents=True, exist_ok=True)
    for path in ASSET_DIR.iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)


def render_index(data: dict) -> str:
    servers = data.get("servers", [])
    rows = []
    for server in servers:
        rows.append(
            "<tr "
            f"data-status='{status_sort_value(server)}' "
            f"data-name='{attr(sort_text(server.get('name')))}' "
            f"data-bigbang='{attr(sort_date(server.get('last_bigbang')))}' "
            f"data-version='{attr(sort_text(server.get('tradewars_version')))}' "
            f"data-games='{attr(sort_number(server.get('game_count')))}' "
            f"data-players='{attr(sort_number(server.get('players')))}'>"
            f"<td class='status-dot'>{led(server)}</td>"
            f"<td><a class='serverlink' href='{server_filename(server)}'>{esc(server.get('name'))}</a></td>"
            f"<td>{esc(server.get('last_bigbang'))}</td>"
            f"<td>{esc(server.get('tradewars_version'))}</td>"
            f"<td class='num'>{esc(server.get('game_count'))}</td>"
            f"<td class='num'>{esc(server.get('players'))}</td>"
            "</tr>"
        )
    body = f"""
<h1>Gone Rogue Tradewars</h1>
{summary_band(data)}
<h2>Game Servers (TWGS v2.x)</h2>
<table class="grid sortable" id="servers-table">
  <thead><tr><th></th><th><button type="button" class="sort-button" data-sort="name" data-type="text">Server</button></th><th><button type="button" class="sort-button" data-sort="bigbang" data-type="number">BigBang</button></th><th><button type="button" class="sort-button" data-sort="version" data-type="text">TradeWars</button></th><th><button type="button" class="sort-button" data-sort="games" data-type="number">Games</button></th><th><button type="button" class="sort-button" data-sort="players" data-type="number">Players</button></th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<script>{SORT_SCRIPT}</script>
"""
    return page("Servers", body, data)


def render_server(data: dict, server: dict) -> str:
    games = display_games(server)
    rows = []
    for game in games:
        game_href = game_filename(server, game)
        game_name = display_game_name(game)
        rows.append(
            "<tr>"
            f"<td><a class='game-link' href='{game_href}'>{esc(game.get('letter'))}</a></td>"
            f"<td><a class='game-link' href='{game_href}'>{esc(game_name)}</a></td>"
            f"<td>{esc(game.get('bigbang'))}</td>"
            f"<td class='{quality_class(days_class(game))}'>{days_cell(game)}</td>"
            f"<td>{esc(game.get('type'))}</td>"
            f"<td class='{quality_class(latency_class(game))}'>{esc(game_latency(game))}</td>"
            f"<td class='{quality_class(delay_class(game))}'>{esc(game_delay(game))}</td>"
            f"<td class='{quality_class(time_class(game))}'>{esc(game.get('time'))}</td>"
            f"<td>{esc(game.get('turns'))}</td>"
            f"<td class='num'>{esc(game.get('sectors'))}</td>"
            f"<td class='num'>{esc(game.get('players'))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='11' class='muted'>No live crawl data yet.</td></tr>")

    body = f"""
<h1>{esc(server.get('name'))}</h1>
<table class="detail">
  <tr><td>Last Update :</td><td>{esc(format_timestamp(server.get('last_crawled_at')))}</td><td>Registered To :</td><td>{esc(server.get('registered_to') or server.get('name'))}</td></tr>
  <tr><td>Telnet :</td><td>{esc(server.get('telnet'))}</td><td>Location :</td><td>{esc(server.get('location', ''))}</td></tr>
  <tr><td>Website :</td><td>{esc(server.get('website', '[Unknown]'))}</td><td>Ventrilo :</td><td>[Unknown]</td></tr>
  <tr><td>GameOP :</td><td>{esc(server.get('gameop', ''))}</td><td>BBS :</td><td>{esc(server.get('bbs'))}</td></tr>
  <tr><td>Type :</td><td>{esc(server.get('type', 'twgs2')).upper()}</td><td>Games :</td><td>{esc(server.get('game_count'))}</td></tr>
  <tr><td>Version :</td><td>{esc(server.get('tradewars_version'))}</td><td>Players :</td><td>{esc(server.get('players'))}</td></tr>
</table>
<p class="note">* = Days Since Start. Live values are generated from TWGS <code>*</code> game stats.</p>
<table class="grid games">
  <thead><tr><th>Game</th><th>Name</th><th>BigBang</th><th>Days*</th><th>Type</th><th>Latency</th><th>Delay</th><th>Time</th><th>Turns</th><th>Sectors</th><th>Players</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<p class="select">Select a game to view game details.</p>
"""
    if server.get("error"):
        body += f"<p class='error'>Last crawl error: {esc(server.get('error'))}</p>"
    return page(str(server.get("name", "Server")), body, data, current=server)


def render_game(data: dict, server: dict, game: dict) -> str:
    raw_stats = game.get("raw_stats") or ""
    game_name = display_game_name(game)
    body = f"""
<p class="breadcrumb"><a href="../index.html">Servers</a> / <a href="../{server_filename(server)}">{esc(server.get('name'))}</a></p>
<h1>{esc(server.get('name'))} - Game {esc(game.get('letter'))}: {esc(game_name)}</h1>
{render_game_stats_panel(server, game)}
<details class="raw-stats">
  <summary>Raw TWGS * stats</summary>
  <pre>{esc(raw_stats or 'No raw stats captured for this game.')}</pre>
</details>
"""
    return page(f"{server.get('name')} {game.get('letter')} {game_name}", body, data, current=server, asset_prefix="../")


def page(title: str, body: str, data: dict, current: dict | None = None, asset_prefix: str = "") -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{esc(title)} - twcrawl</title>
  <link rel="stylesheet" href="{asset_prefix}style.css">
</head>
<body>
  <div class="shell">
    <main>
      <section class="content">{body}</section>
    </main>
    <footer>Generated by twcrawl. TradeWars is a registered trademark of Epic Interactive Strategy.</footer>
  </div>
</body>
</html>
"""


def summary_band(data: dict) -> str:
    servers = data.get("servers", [])
    total_games = sum(int(server.get("game_count") or 0) for server in servers)
    total_players = sum(int(server.get("players") or 0) for server in servers)
    return (
        "<div class='summary'>"
        f"<span>Servers: {len(servers)}</span>"
        f"<span>Games: {total_games}</span>"
        f"<span>Players: {total_players}</span>"
        f"<span>Last Crawl: {esc(format_timestamp(data.get('generated_at')))}</span>"
        "</div>"
    )


def server_filename(server: dict) -> str:
    return f"server-{server.get('server_id', server.get('slug', 'server'))}.html"


def game_filename(server: dict, game: dict) -> str:
    return f"{game_directory(server)}/game-{str(game.get('letter', 'game')).lower()}.html"


def display_games(server: dict) -> list[dict]:
    return [
        game
        for game in server.get("games") or []
        if game.get("status") == "ok" or game.get("stats") or game.get("raw_stats")
    ]


def display_game_name(game: dict) -> str:
    raw_name = str(game.get("name") or "")
    return clean_menu_game_name(raw_name) or raw_name


def game_directory(server: dict) -> str:
    server_id = server.get("server_id", server.get("slug", "server"))
    return f"server-{server_id}"


def led(server: dict) -> str:
    status = server.get("status")
    is_up = status == "online"
    color = "green" if is_up else "red"
    title = "Up on last crawl" if is_up else "Down on last crawl"
    return f"<span title='{title}' class='led {color}'></span>"


def status_sort_value(server: dict) -> str:
    return "1" if server.get("status") == "online" else "0"


def days_cell(game: dict) -> str:
    days = game.get("days_open")
    return "" if days is None else str(days)


def days_class(game: dict) -> str:
    days = game.get("days_open")
    if days is None:
        return ""
    try:
        value = int(days)
    except (TypeError, ValueError):
        return ""
    if value < 60:
        return "good"
    if value <= 120:
        return "warn"
    return "bad"


def time_class(game: dict) -> str:
    value = str(game.get("time") or "").strip().lower()
    if not value:
        return ""
    return "good" if value == "unlimited" else "bad"


def game_latency(game: dict) -> str:
    return str((game.get("stats") or {}).get("Latency") or "")


def latency_class(game: dict) -> str:
    value = game_latency(game)
    match = re.search(r"\d+", value)
    if not match:
        return ""
    milliseconds = int(match.group(0))
    if milliseconds <= 150:
        return "good"
    if milliseconds <= 250:
        return "warn"
    return "bad"


def game_delay(game: dict) -> str:
    raw_value = ship_delay_value(game)
    if delay_word(game) == "constant":
        duration = re.search(r"\(([^)]*)\)", raw_value)
        if duration:
            return duration.group(1).strip().lower()
    return delay_word(game)


def delay_class(game: dict) -> str:
    value = delay_word(game)
    if not value:
        return ""
    if value == "none" or (value == "constant" and constant_delay_milliseconds(game) <= 250):
        return "good"
    if value in {"quarter", "third"}:
        return "warn"
    if value in {"half", "double", "constant"}:
        return "bad"
    return "bad"


def constant_delay_milliseconds(game: dict) -> int:
    raw_value = ship_delay_value(game)
    match = re.search(r"\((\d+)\s*(ms|msec|millisecond|milliseconds|s|sec|secs|second|seconds|min|mins|minute|minutes)\)", raw_value, re.IGNORECASE)
    if not match:
        return 251
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("m") and unit not in {"min", "mins", "minute", "minutes"}:
        return amount
    if unit.startswith("s"):
        return amount * 1000
    return amount * 60000


def delay_word(game: dict) -> str:
    match = re.search(r"[A-Za-z]+", ship_delay_value(game))
    return match.group(0).lower() if match else ""


def ship_delay_value(game: dict) -> str:
    return str((game.get("stats") or {}).get("Ship Delay") or "")


def quality_class(value: str) -> str:
    return f"quality {value}".strip()


def format_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%m/%d/%Y")
    except ValueError:
        return value


def sort_date(value: object) -> str:
    if not value:
        return "0"
    try:
        return str(int(datetime.strptime(str(value), "%m/%d/%Y").timestamp()))
    except ValueError:
        return "0"


def sort_number(value: object) -> str:
    if value is None:
        return "0"
    return "".join(ch for ch in str(value) if ch.isdigit() or ch == "-") or "0"


def sort_text(value: object) -> str:
    return "" if value is None else str(value).casefold()


def esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def attr(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_game_stats_panel(server: dict, game: dict) -> str:
    stats = game.get("stats") or parse_stats_sections(game.get("raw_stats") or "").get("_flat", {})
    if not stats:
        return "<p class='muted'>No live game stats have been captured for this game.</p>"

    sections = [
        [
            pair("Registered to", server.get("registered_to") or server.get("name")),
            pair("Version", long_game_version(stats, game), "Host type", host_type(server)),
            pair("Age of game", stat(stats, "Game Age", game.get("days_open")), "Days since start", stat(stats, "Game Age", game.get("days_open"))),
            pair("Delete if idle", stat(stats, "Days Til Deletion")),
        ],
        [
            pair("Players in game", active_of_max(stats, "Active Players", "Users"), "Percent good", percent_value(stat(stats, "Percent Players Good"))),
            pair("Aliens in game", active_of_max(stats, "Active Aliens", "Aliens"), "Percent good", percent_value(stat(stats, "Percent Aliens Good"))),
            pair("Ports in game", active_of_max(stats, "Active Ports", "Ports"), "Value of ports", stat(stats, "Port Value")),
            pair("Planets in game", active_of_max(stats, "Active Planets", "Planets"), "Percent w/ Citadels", percent_value(stat(stats, "Percent Planet Citadels"))),
            pair("Ships in game", active_of_max(stats, "Active Ships", "Ships"), "Corps in game", stat(stats, "Active Corps")),
            pair("Figs in game", stat(stats, "Active Figs"), "Mines in game", stat(stats, "Active Mines")),
        ],
        [
            pair("Game type", game.get("type") or game_type(stats), "Game time", game_time(stat(stats, "Local Game Time"))),
            pair("Time per day", stat(stats, "Time Online", game.get("time")), "Turns per day", strip_turns(stat(stats, "Turn Base", game.get("turns")))),
            pair("Planetary Trade %", percent_value(stat(stats, "Trade Percent")), "Steal from BUY port", yes_no(stat(stats, "Steal Buy"))),
            pair("Initial fighters", stat(stats, "Initial Fighters"), "Clear Busts Every", stat(stats, "Clear Bust Days")),
            pair("Initial credits", comma_int(stat(stats, "Initial Credits")), "Last Bust Clear", last_bust_clear(stats)),
            pair("Initial holds", stat(stats, "Initial Holds"), "Multiple Photon fire", yes_no(stat(stats, "Multiple Photons"))),
            pair("Sectors in game", stat(stats, "Sectors", game.get("sectors")), "Display StarDock", yes_no(stat(stats, "Show Stardock"))),
            pair("Start with planet", yes_no(stat(stats, "New Player Planets")), "Classic Ferrengi", yes_no(stat(stats, "Internal Ferrengi"))),
            pair("Production Rate", production_rate(stats), "Max Regen per Visit", percent_value(stat(stats, "Max Production Regen"))),
            pair("Tournament Mode", tournament_mode(stat(stats, "Tournament Mode")), "Invincible Ferrengal", yes_no(stat(stats, "Invincible Ferengal"))),
        ],
    ]

    body = "<div class='tw-panel'>"
    for group in sections:
        body += render_stat_rows(group)
        body += "<div class='tw-gap'></div>"
    body += section_title("Report Settings")
    body += render_stat_rows(
        [
            pair("High Score Mode", stat(stats, "High Score Mode"), "High Score Type", stat(stats, "High Score Type")),
            pair("Rankings Mode", stat(stats, "Rankings Mode"), "Rankings Type", stat(stats, "Rankings Type")),
            pair("Entry Log Blackout", stat(stats, "Entry Log Blackout"), "Game Log Blackout", stat(stats, "Game Log Blackout")),
            pair("Port Report Delay", stat(stats, "Port Report Delay")),
        ]
    )
    body += "<div class='tw-gap'></div>"
    body += section_title("Delays")
    body += render_stat_rows(
        [
            pair("Ship Attack/Move", stat(stats, "Ship Delay"), "Planet Move", stat(stats, "Planet Delay")),
            pair("Other Attack", stat(stats, "Other Attacks Delay"), "Rob/Steal", stat(stats, "Crime Delay")),
            pair("Photon Launch", stat(stats, "Photon Launch Delay"), "Photon Blast", stat(stats, "Photon Wave Delay")),
            pair("Ship IG", stat(stats, "IC Powerup Delay"), "Planetary IG", stat(stats, "PIG Powerup Delay")),
            pair("Dock/Depart", stat(stats, "Port Dock/Depart Delay"), "Land/Takeoff", stat(stats, "Planet Landing/Takeoff Delay")),
            pair("Drop/Take Mines", stat(stats, "Drop/Take Mines Delay"), "Drop/Take Figs", stat(stats, "Take/Drop Fighters Delay")),
            pair("Planet Transport", stat(stats, "Planet Transporter Delay"), "Ship Transport", stat(stats, "Ship Transporter Delay")),
            pair("EtherProbe Move", stat(stats, "EProbe Delay"), "GenTorp Launch", stat(stats, "Genesis Launch Delay")),
        ]
    )
    body += "<div class='tw-gap'></div>"
    body += section_title("IO Emulation")
    body += render_stat_rows(
        [
            pair("Input Bandwidth", stat(stats, "Input Bandwidth")),
            pair("Output Bandwidth", stat(stats, "Output Bandwidth")),
            pair("Latency", stat(stats, "Latency")),
        ]
    )
    body += render_additional_stats(stats)
    body += "</div>"
    return body


def render_stat_rows(rows: list[dict]) -> str:
    return "".join(
        "<div class='tw-row'>"
        f"{render_pair(row['left_label'], row['left_value'])}"
        f"{render_pair(row.get('right_label'), row.get('right_value'))}"
        "</div>"
        for row in rows
    )


def render_pair(label: object, value: object) -> str:
    if not label:
        return "<div class='tw-pair'></div>"
    return (
        "<div class='tw-pair'>"
        f"<span class='tw-label'>{esc(label)}</span>"
        "<span class='tw-colon'>:</span>"
        f"<span class='tw-value'>{value_markup(value)}</span>"
        "</div>"
    )


def pair(left_label: object, left_value: object = "", right_label: object | None = None, right_value: object = "") -> dict:
    return {
        "left_label": left_label,
        "left_value": left_value,
        "right_label": right_label,
        "right_value": right_value,
    }


def section_title(title: str) -> str:
    return f"<h2 class='tw-section'>{esc(title)}</h2>"


def render_additional_stats(stats: dict[str, str]) -> str:
    cost_keys = [
        "Tavern Announcement",
        "Limpet Removal",
        "Reregister Ship",
        "Citadel Transport Unit",
        "Citadel Transport Upgrade",
        "Genesis Torpedo",
        "Armid Mine",
        "Limpet Mine",
        "Beacon",
        "Type I TWarp",
        "Type II TWarp",
        "TWarp Upgrade",
        "Psychic Probe",
        "Planet Scanner",
        "Atomic Detonator",
        "Corbomite",
        "Ether Probe",
        "Photon Missile",
        "Cloaking Device",
        "Mine Disruptor",
        "Holographic Scanner",
        "Density Scanner",
    ]
    present = [(key, stats.get(key)) for key in cost_keys if stats.get(key)]
    if not present:
        return ""
    rows = []
    for index in range(0, len(present), 2):
        left = present[index]
        right = present[index + 1] if index + 1 < len(present) else ("", "")
        rows.append(pair(left[0], left[1], right[0], right[1]))
    return "<div class='tw-gap'></div>" + section_title("Costs") + render_stat_rows(rows)


def parse_stats_sections(raw_stats: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {"_flat": {}}
    current = "_flat"
    for raw_line in raw_stats.splitlines():
        line = raw_line.strip()
        if not line or line in {"Game Stats:", "End Stats."}:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        sections.setdefault(current, {})[key] = value
        sections["_flat"][key] = value
    return sections


def stat(stats: dict[str, str], key: str, default: object = "") -> object:
    value = stats.get(key)
    return default if value in {None, ""} else value


def long_game_version(stats: dict[str, str], game: dict) -> str:
    major = stat(stats, "Major Version")
    minor = stat(stats, "Minor Version")
    revision = stat(stats, "Revision")
    version = f"{major}.{minor}{revision}" if major and minor else str(game.get("version") or "")
    suffixes = []
    if yes_no(stat(stats, "MBBS Compatibility")) == "Yes":
        suffixes.append("MBBS")
    if yes_no(stat(stats, "Gold Enabled")) == "Yes":
        suffixes.append("Gold")
    return " ".join([version, *suffixes]).strip()


def host_type(server: dict) -> str:
    server_type = str(server.get("type") or "").lower()
    if server_type == "twgs2":
        return "TWGS v2"
    return str(server.get("tradewars_version") or server.get("type") or "")


def active_of_max(stats: dict[str, str], active_key: str, max_key: str) -> str:
    active = stat(stats, active_key)
    max_value = stat(stats, max_key)
    if max_value in {None, ""}:
        return str(active)
    return f"{active} of max {max_value}"


def percent_value(value: object) -> str:
    text = str(value or "")
    if not text or text.upper() == "N/A" or text.endswith("%"):
        return text
    return f"{text}%"


def yes_no(value: object) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered == "true":
        return "Yes"
    if lowered == "false":
        return "No"
    return text


def strip_turns(value: object) -> str:
    return str(value or "").replace(" Turns", "")


def comma_int(value: object) -> str:
    text = str(value or "").replace(",", "")
    if not text.isdigit():
        return str(value or "")
    return f"{int(text):,}"


def production_rate(stats: dict[str, str]) -> str:
    value = percent_value(stat(stats, "Production Rate"))
    return f"{value} / Day" if value else ""


def tournament_mode(value: object) -> str:
    text = str(value or "")
    return "Off" if text == "0" else text


def game_type(stats: dict[str, str]) -> str:
    return "Closed" if yes_no(stat(stats, "Closed Game")) == "Yes" else "Open"


def game_time(value: object) -> str:
    text = str(value or "")
    parts = text.split(" ", 1)
    return parts[1] if len(parts) == 2 else text


def last_bust_clear(stats: dict[str, str]) -> str:
    clear_day = str(stat(stats, "Last Bust Clear Day") or "")
    local_time = str(stat(stats, "Local Game Time") or "")
    if clear_day and local_time.startswith(clear_day):
        return "Today"
    return clear_day


def value_markup(value: object) -> str:
    text = esc(value)
    text = rewrap_parenthetical(text)
    if text == "Today":
        return "<span class='tw-hot'>Today</span>"
    return text


def rewrap_parenthetical(text: str) -> str:
    return re.sub(r"(\([^)]*\))", r"<span class='tw-hot'>\1</span>", text)


SORT_SCRIPT = """
(() => {
  const table = document.getElementById("servers-table");
  if (!table) return;
  const tbody = table.querySelector("tbody");
  const directions = {};
  const defaults = { text: 1, number: -1 };

  function value(row, key, type) {
    const raw = row.dataset[key] || "";
    return type === "number" ? Number(raw) || 0 : raw;
  }

  table.querySelectorAll(".sort-button").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sort;
      const type = button.dataset.type || "text";
      const current = directions[key] || 0;
      const direction = current ? current * -1 : defaults[type];
      directions[key] = direction;

      table.querySelectorAll(".sort-button").forEach((other) => {
        other.removeAttribute("aria-sort");
      });
      button.setAttribute("aria-sort", direction === 1 ? "ascending" : "descending");

      const rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort((left, right) => {
        const leftValue = value(left, key, type);
        const rightValue = value(right, key, type);
        if (leftValue < rightValue) return -1 * direction;
        if (leftValue > rightValue) return 1 * direction;
        return (left.dataset.name || "").localeCompare(right.dataset.name || "");
      });
      rows.forEach((row) => tbody.appendChild(row));
    });
  });
})();
"""


STYLE = """
html, body { margin: 0; min-height: 100%; color: #999; font: 13px Verdana, Arial, sans-serif; }
body { background: #000 url("assets/stars-galaxy-3840x2160-10307.jpg") center top / cover fixed no-repeat; }
body::before { content: ""; position: fixed; inset: 0; background: rgba(0, 0, 0, 0.58); pointer-events: none; z-index: -1; }
a { color: #777; text-decoration: none; }
a:hover { color: #aaa; }
.shell { width: 900px; margin: 0 auto; padding-top: 10px; }
main { display: block; }
.content { min-width: 0; }
h1 { color: #099; font-size: 20px; margin: 10px 0 18px; text-align: center; }
h2 { color: #099; font-size: 14px; margin: 18px 0 8px; text-align: center; }
.summary { border: 1px solid #1f3030; background: rgba(0, 8, 10, 0.82); padding: 8px; margin-bottom: 14px; display: flex; gap: 18px; justify-content: center; color: #aaa; }
table { border-collapse: collapse; width: 100%; }
.grid { background: rgba(0, 5, 7, 0.84); border: 1px solid rgba(0, 153, 153, 0.22); }
.grid th { color: #0aa; font-weight: bold; border-bottom: 1px solid rgba(0, 153, 153, 0.28); padding: 4px 5px; text-align: left; background: rgba(0, 15, 18, 0.9); }
.grid td { padding: 4px 5px; border-bottom: 1px solid rgba(0, 153, 153, 0.12); color: #18b018; }
.grid tr:nth-child(even) td { color: #62ff62; background: rgba(0, 20, 22, 0.28); }
.grid .num, .num { text-align: center; }
.grid td.quality.good { color: #42ff65; }
.grid td.quality.warn { color: #ffff66; }
.grid td.quality.bad { color: #ff5f5f; }
.sort-button { appearance: none; background: transparent; border: 0; color: #099; cursor: pointer; font: inherit; font-weight: bold; padding: 0; }
.sort-button:hover { color: #0cc; }
.sort-button[aria-sort="ascending"]::after { content: " ▲"; color: #777; }
.sort-button[aria-sort="descending"]::after { content: " ▼"; color: #777; }
.status-dot { width: 22px; text-align: center; }
.serverlink { color: #a8d9e8; font-weight: normal; }
.serverlink:hover { color: #d8f3ff; }
.game-link { color: #9ee7f1; font-weight: normal; }
.game-link:hover { color: #d8f9ff; }
.detail { margin: 4px auto 12px; width: 650px; background: rgba(0, 5, 7, 0.84); border: 1px solid rgba(0, 153, 153, 0.22); }
.detail td { padding: 3px 7px; color: #999; }
.detail td:nth-child(odd) { color: #777; text-align: right; white-space: nowrap; }
.breadcrumb { color: #777; margin: 2px 0 10px; }
.breadcrumb a { color: #0aa; }
.tw-panel { margin: 0 auto 14px; padding: 12px 14px; background: rgba(0, 0, 0, 0.86); border-left: 4px solid rgba(0, 153, 153, 0.62); border-right: 4px solid rgba(0, 153, 153, 0.62); box-shadow: inset 0 0 0 1px rgba(0, 153, 153, 0.24); color: #0f0; font: 16px "Courier New", Consolas, monospace; line-height: 1.22; overflow-x: auto; }
.tw-row { display: grid; grid-template-columns: minmax(320px, 1fr) minmax(320px, 1fr); gap: 36px; min-width: 760px; }
.tw-pair { display: grid; grid-template-columns: 18ch 1ch 1fr; column-gap: 1ch; min-height: 1.22em; }
.tw-label, .tw-colon { color: #00c020; }
.tw-value { color: #00f5f5; white-space: pre; }
.tw-hot { color: #ffff00; }
.tw-section { color: #d000d0; font: inherit; margin: 18px 0 10px; text-align: left; }
.tw-gap { height: 16px; }
.raw-stats { margin: 12px 0; padding: 8px 10px; background: rgba(0, 5, 7, 0.82); border: 1px solid rgba(0, 153, 153, 0.22); }
.raw-stats summary { color: #0aa; cursor: pointer; }
.raw-stats pre { max-height: 520px; overflow: auto; color: #aaa; font: 12px "Courier New", Consolas, monospace; white-space: pre-wrap; }
.note, .select, .muted { color: #888; }
.error { color: #c66; }
.led { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: -1px; border: 1px solid #111; }
.led.green { background: #00a000; box-shadow: 0 0 4px #00a000; }
.led.red { background: #8a1010; box-shadow: 0 0 4px #8a1010; }
.led.dim { background: #303030; }
.led.purple { background: #6c3fb8; }
.led.blue { background: #4ba3d9; }
code { color: #aaa; }
footer { text-align: center; color: #666; padding: 24px 0; font-size: 11px; }
@media (max-width: 940px) {
  .shell { width: auto; margin: 0 10px; }
  .tw-panel { font-size: 14px; }
}
"""
