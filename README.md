# twcrawl

`twcrawl` is a standalone TradeWars Game Server crawler that recreates the
defunct MicroBlaster server-list workflow:

1. Read a JSON seed list of known TWGS servers.
2. Open a telnet connection to each server.
3. Login with the crawler name, request TWGS `$` XML game data when available,
   then enter playable games to capture `H` active-player high scores. When XML
   is unavailable, fall back to pressing `*` for `Game Stats` before `H`.
4. Store the crawl result in JSON.
5. Generate static MicroBlaster-style HTML pages.

The initial seed list is imported from the archived MicroBlaster
`servers.aspx` TWGS v2 table.

## Quick start - Windows PowerShell

```powershell
cd C:\path\to\twcrawl
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .

twcrawl init-seeds
twcrawl crawl --only "Gone Rogue" --build
twcrawl serve
```

If PowerShell script execution blocks activation, either run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

or skip activation and call the venv Python directly:

```powershell
.\.venv\Scripts\python.exe -m twcrawl init-seeds
.\.venv\Scripts\python.exe -m twcrawl crawl --only "Gone Rogue" --build
.\.venv\Scripts\python.exe -m twcrawl serve
```

Open `http://127.0.0.1:8008/`.

## Quick start - macOS/Linux

```bash
cd /path/to/twcrawl
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

twcrawl init-seeds
twcrawl crawl --only "Gone Rogue" --build
twcrawl serve
```

Open `http://127.0.0.1:8008/`.

## Commands

```bash
twcrawl init-seeds
twcrawl add-server games.opentw.org 2002 OpenTW
twcrawl crawl --all --build
twcrawl crawl --missing --build
twcrawl crawl --only "Gone Rogue" --build
twcrawl build
twcrawl serve --port 8008
twcrawl online Freejack
twcrawl search --player Freejack
twcrawl search --edit SubZero
twcrawl daily
twcrawl monitor-mtc
```

The same commands can also be run as a Python module on any platform:

```bash
python -m twcrawl init-seeds
python -m twcrawl add-server games.opentw.org 2002 OpenTW
python -m twcrawl crawl --all --build
python -m twcrawl crawl --missing --build
python -m twcrawl serve --port 8008
python -m twcrawl online Freejack --json
python -m twcrawl search --player Freejack
python -m twcrawl monitor-mtc --json
```

By default the crawler stores state in `data/twcrawl.json` and generates pages
under `public/`.

## Adding servers

Use `twcrawl add-server` with only the host or IP address, telnet port, and
server display name:

```bash
twcrawl add-server games.opentw.org 2002 OpenTW
twcrawl add-server 192.0.2.10 2002 "My TWGS"
```

Names with spaces can be quoted, or passed as separate trailing words:

```bash
twcrawl add-server games.example.net 2002 My TWGS
```

The command adds or updates the server in `data/twcrawl.json`, which is the
active crawler database used by `crawl --only`. It also updates the local
`data/servers.seed.json` by default so the server is kept if you later rebuild
the active data from seeds. Both files are local runtime data and are ignored
by git.

After adding a server, crawl it:

```bash
twcrawl crawl --only OpenTW --build
```

Or do it in one step:

```bash
twcrawl add-server games.opentw.org 2002 OpenTW --crawl --build
```

Use `--no-seeds` if you only want to modify the active `data/twcrawl.json`
file.

## Daily runs and history

`twcrawl daily` is the one-command scheduler entry point. It runs a crawl,
writes `data/twcrawl.json`, rebuilds `public/`, and stores a timestamped JSON
snapshot under `data/history/`:

```bash
twcrawl daily
twcrawl daily --mode missing
twcrawl daily --no-build
twcrawl daily --only "Gone Rogue"
```

The latest history snapshot is also copied to `data/history/latest.json`, and a
small `data/history/manifest.json` lists the saved snapshots. These runtime
history files are intentionally ignored by git.

On macOS/Linux, run it daily from cron with a line like:

```cron
15 4 * * * cd /path/to/twcrawl && /path/to/twcrawl/.venv/bin/twcrawl daily >> data/logs/daily.log 2>&1
```

On Windows Task Scheduler, create a daily task whose action is:

```text
Program: C:\path\to\twcrawl\.venv\Scripts\twcrawl.exe
Arguments: daily
Start in: C:\path\to\twcrawl
```

## Search

`twcrawl search` searches the current crawler data. Use positional text or
`--edit` for game/edit/template/config text, and `--player` for high-score
player names:

```bash
twcrawl search SubZero
twcrawl search --edit "Poker Run"
twcrawl search --player Freejack
twcrawl search --server "The City" --player reaper
twcrawl search --json --player Freejack
```

Text search covers server identity, game name, original menu name, basic table
fields, and parsed `*` stats keys/values.

## MTC recent-game monitor

`twcrawl monitor-mtc` scans MTC game config files modified in the last 60 days
under `/Users/mosleym/twx/games`, matches them to crawled twcrawl games by
`Host:Port` plus `GameLetter`, compares the current high-score player list with
the previous monitor state, and checks who is currently online by sending `#`
at each matched TWGS server menu.

```bash
twcrawl monitor-mtc
twcrawl monitor-mtc --days 30
twcrawl monitor-mtc --no-live
twcrawl monitor-mtc --json
```

State is stored in `data/monitors/mtc-recent.json`; the last full report is
stored beside it as `data/monitors/mtc-recent-last-report.json`. On the first
run, each matched game creates a baseline. Later runs report players who appear
in a game's high scores that were not present during the previous monitor run,
plus currently logged-in players from the live `#` check.

## REST/API output

`twcrawl build` also writes static JSON API files under `public/api/`, so the
same Apache site that serves the HTML pages can serve crawler data over HTTPS
without running a separate Python process.

Useful Apache-served JSON endpoints:

```text
/api/index.json
/api/health.json
/api/data.json
/api/servers.json
/api/servers/{server_id}.json
/api/servers/{server_id}/games.json
/api/servers/{server_id}/games/{letter}.json
/api/games.json
/api/configurations.json
/api/players.json
/api/players/{player_slug}.json
/api/players/{player_slug}/games.json
```

`/api/data.json` contains the full crawler database. `/api/games.json` is a
flattened game list with server identity fields for clients such as MTC.
`/api/configurations.json` exposes each game's parsed configuration values and
raw `*` stats block when captured. Full per-game records also include
`high_scores`, `raw_high_scores`, and any TWGS `$` XML data as `xml` /
`raw_xml`; summary game records include `active_player_names` and
`high_score_count`.

To find games by active player on Apache, fetch `/api/players.json`, find the
matching player `slug`, then fetch `/api/players/{player_slug}/games.json`.
These player lookup files are generated for API clients but are not linked from
the public pages.

For local development, `twcrawl serve` also provides live extensionless REST
routes that reload `data/twcrawl.json` on each request:

```text
/api
/api/health
/api/data
/api/servers
/api/servers/{server_id_or_slug}
/api/servers/{server_id_or_slug}/games
/api/servers/{server_id_or_slug}/games/{letter}
/api/games
/api/configurations
/api/players
/api/players/{player_slug_or_name}
/api/players/{player_slug_or_name}/games
```

List endpoints accept `full=1`; `/api/games` and `/api/configurations` also
accept `server=`, `player=`, and `status=` filters. The `player=` filter is a
case-insensitive active-player name substring match.

Use `twcrawl crawl --missing --build` to retry only servers without current
usable data. A server is considered missing current data when its last crawl did
not finish online, it has never been crawled, it has no crawled game rows, or
any game row has a non-`ok` status.

Use `twcrawl online PLAYER` to do a live login check for a player already known
from high-score crawl data. It connects only to servers where that player is in
the generated player index, sends `#` at the TWGS server menu, and reports which
known games the player is currently logged in to versus not logged in to.

`data/servers.seed.json` is local generated configuration and is intentionally
not tracked by git. Run `twcrawl init-seeds` once to create it, then edit it for
your server list. Future git pulls will not overwrite it. To intentionally
regenerate it from the archived MicroBlaster list, run:

```bash
twcrawl init-seeds --force
```

## Notes

- The crawler and web server are cross-platform Python code. They use only the
  Python standard library plus the package metadata in `pyproject.toml`.
- When a TWGS server supports `$`, the XML response is used as the preferred
  server/game source. It exposes cleaner game names and configured games that
  may not appear on the normal menu yet; closed games are stored but not entered.
- TWGS expects real telnet negotiation. `twcrawl` sends the same initial telnet
  handshake style used by TWX/MTC and responds to terminal type, NAWS, and
  suppress-go-ahead options.
- Game version display follows MicroBlaster convention: `Major.Minor` plus `G`
  for Gold Enabled and `M` for MBBS Compatibility.
- TWGS `mm/dd/yy` dates use the in-game year. The crawler maps the local game
  year from `Local Game Time` to the crawl timestamp year, so current servers
  render as normal calendar years.
