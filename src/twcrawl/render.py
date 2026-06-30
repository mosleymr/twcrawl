from __future__ import annotations

import html
import shutil
from datetime import datetime
from pathlib import Path


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
    games = server.get("games") or []
    rows = []
    for game in games:
        rows.append(
            "<tr>"
            f"<td>{esc(game.get('letter'))}</td>"
            f"<td>{esc(game.get('name'))}</td>"
            f"<td>{esc(game.get('bigbang'))}</td>"
            f"<td>{days_cell(game)}</td>"
            f"<td>{esc(game.get('type'))}</td>"
            f"<td>{esc(game.get('version'))}</td>"
            f"<td>{esc(game.get('emulation'))}</td>"
            f"<td>{esc(game.get('time'))}</td>"
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
  <thead><tr><th>Game</th><th>Name</th><th>BigBang</th><th>Days*</th><th>Type</th><th>Version</th><th>Emulation</th><th>Time</th><th>Turns</th><th>Sectors</th><th>Players</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<p class="select">Select a game to view game details.</p>
"""
    if server.get("error"):
        body += f"<p class='error'>Last crawl error: {esc(server.get('error'))}</p>"
    return page(str(server.get("name", "Server")), body, data, current=server)


def page(title: str, body: str, data: dict, current: dict | None = None) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{esc(title)} - twcrawl</title>
  <link rel="stylesheet" href="style.css">
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
.sort-button { appearance: none; background: transparent; border: 0; color: #099; cursor: pointer; font: inherit; font-weight: bold; padding: 0; }
.sort-button:hover { color: #0cc; }
.sort-button[aria-sort="ascending"]::after { content: " ▲"; color: #777; }
.sort-button[aria-sort="descending"]::after { content: " ▼"; color: #777; }
.status-dot { width: 22px; text-align: center; }
.serverlink { color: #a8d9e8; font-weight: normal; }
.serverlink:hover { color: #d8f3ff; }
.detail { margin: 4px auto 12px; width: 650px; background: rgba(0, 5, 7, 0.84); border: 1px solid rgba(0, 153, 153, 0.22); }
.detail td { padding: 3px 7px; color: #999; }
.detail td:nth-child(odd) { color: #777; text-align: right; white-space: nowrap; }
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
"""
