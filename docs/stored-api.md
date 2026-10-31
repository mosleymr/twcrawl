# Stored API and Crawl History

## Architecture

Each `crawl` or `daily` command commits a complete snapshot and a change report
to SQLite before atomically replacing the existing JSON data file. The default
archive is `data/twcrawl.sqlite3`, beside `data/twcrawl.json`. Use the same
`--data` and `--database` paths for the crawler and API process. No external
database server or Python packages are required.

`twcrawl serve --api-only` reads the latest committed SQLite record for every
request. It does not contact game servers, rebuild pages, or read exported
`public/api` indexes. A running API sees new completed crawls without a restart.
While a crawl is in progress, clients see the previous complete snapshot.
Failed servers retain their last known games, with failure and freshness fields.

The archive is outside `public` and ignored by Git. Back it up using SQLite's
backup API or stop writers before copying the database and its WAL files. Do
not put the database or the crawler checkout under Apache's document root.
Snapshots are retained indefinitely; monitor disk usage.

## Start or Migrate

Run these commands from the checkout, using its installed `twcrawl` launcher
or `python -m twcrawl` in the appropriate Python environment:

```text
twcrawl archive
twcrawl serve --api-only --host 127.0.0.1 --port 8008
```

`archive` imports the existing JSON as a baseline without crawling or building.
`serve` also imports automatically if the archive does not exist. Existing JSON
history files remain untouched; the SQLite archive starts with the imported
current snapshot and records subsequent crawls. Existing seed files are not
replaced.

```text
twcrawl daily --no-build
twcrawl report
twcrawl report --run 1
```

The daily command crawls all configured servers and archives the result. Omit
`--no-build` to continue publishing the legacy generated pages too. Existing
`crawl --all --build` jobs also populate SQLite automatically. Do not schedule
overlapping crawls against the same data file. On Windows, use Task Scheduler
with the checkout as the working directory, the existing Python environment,
and the option to skip starting a new instance while one is running. Configure
the API to start at boot and restart on failure. Cygwin installations must use
their Cygwin Python and paths, rather than mixing them with native Windows ones.

For an existing Cygwin cron installation, `python3 deploy/cygwin-api.py --ensure`
starts a detached loopback API with output in `data/logs/api.log`.
`python3 deploy/cygwin-api.py --install-cron` backs up the current user's cron
and adds boot startup plus a five-minute health watchdog without changing
existing crawl jobs. This uses the existing account, not a new Windows service.

## Apache

Keep the existing HTTPS certificate and `/games` static pages. Enable Apache's
`proxy_module` and `proxy_http_module`, then include `deploy/apache-api.conf`
inside the HTTPS virtual host. Place it before catch-all proxy/rewrite rules.
Existing rewrite fallbacks must exclude `/api`. Test the Apache configuration
before a graceful restart. No public Python port or firewall exception is needed.

On the roguetw Apache layout, preview the exact backed-up configuration change:

```text
python3 deploy/apache-setup.py --apache-root /cygdrive/c/Apache24 --server-name roguetw.net
```

After reviewing the preview, add `--apply --restart`. The helper leaves TLS
settings untouched, backs up changed files with a timestamp, and restores them
if Apache's configuration test fails. It expects the existing HTTPS virtual
host in `conf/extra/httpd-ssl.conf`. Use manual configuration for other layouts.

MTC continues to use `/api`, including `/api/games.json`. Both extensionless
and `.json` endpoints read SQLite; a stale `htdocs/api` export is not consulted.
The old static files may stay in place for rollback. Remove the proxy include
and reload Apache to return to those files if needed.

The API is read-only and has no built-in authentication. Its data consists of
public server/game records, public high scores, and sampled online users.
Protect selected routes with Apache authentication if they should not be public.
Do not expose the loopback listener directly to the Internet.

## Routes

All responses are JSON and support GET/HEAD. Writes return 405. CORS allows
browser reads. Responses have `Cache-Control: no-store`.

| Request | Result |
| --- | --- |
| `/api/health` | Generation timestamp, committed run ID, storage, server count |
| `/api/servers?full=1` | Server records, including status and last success |
| `/api/servers/{id}` | Full server record and games |
| `/api/games?player=Freejack` | Games whose high scores contain that player |
| `/api/games?edit=SubZero` | Search game/edit/configuration text |
| `/api/games?server=ice9&full=1` | Filtered games with stats, raw data, rosters |
| `/api/servers/{id}/games/{letter}` | Full game details |
| `/api/configurations?player=Freejack` | Matching game configurations |
| `/api/players` | Known player index |
| `/api/players/{name-or-slug}/games` | Known games for one player |
| `/api/online?player=Freejack` | Last sampled online sessions |
| `/api/activity?server=ice9&letter=A` | Filtered sampled online sessions and check status |
| `/api/reports/latest` | Latest change report, failures, and sampled activity |
| `/api/runs?limit=50&before=123` | Run metadata, newest first; limit capped at 200 |
| `/api/runs/{id}` | Historical snapshot and report |
| `/api/runs/{id}/report` | Historical change report |
| `/api/data` | Entire current stored snapshot |

Append `.json` for compatibility, for example `/api/reports/latest.json`.
URL-encode names. Player matching is case-insensitive substring matching on game
searches; player detail routes resolve a specific known player. `player` means
presence in high scores, not necessarily logged in now.

Online checks are captured once per server during a crawl with `#`. Each
session/check has `checked_at`; a failed check is unknown, not proof of no users.
The crawler's own menu connection is excluded. The data is a sample, not a
continuous presence feed. API requests never initiate a fresh check.

Change reports list new games, removed games, rebangs, newly seen high-score
players, and online presence changes. A rebang does not label all of its players
as new. Unavailable previous rosters establish a baseline. Offline or incomplete
server checks do not count as game removals or online departures. Every API
consumer should display timestamps and retained failures alongside its results.

## Browser Example

### Activity Page

`https://roguetw.net/active.html` reads the stored API directly. It offers change
reports, grouped online samples, game/edit/player search, server-check details,
and historical run selection. The latest view checks for updates every five
minutes while the tab is visible; archived views stay on the selected run.
It never initiates a crawl. API failures retain the displayed snapshot with a
warning, and old latest snapshots receive a stale-data warning.

Source lives in `src/twcrawl/web/`. `twcrawl build` writes `public/active.html`
and its two assets without embedding any crawl data. For the top-level Apache
page, deploy from the checkout with:

```text
python3 deploy/publish-active.py --document-root /cygdrive/c/apache24/htdocs
```

The publisher copies only `active.html`, `assets/twcrawl-active.css`, and
`assets/twcrawl-active.js`. Existing versions are backed up in `data/logs/`.
It does not replace the server list, API files, homepage, or crawl database.
The page uses the shared `/games/style.css` and its existing star background.
The latest report's JSON link always identifies the displayed immutable run.

### Fetching Games

```javascript
const response = await fetch('/api/games?player=' + encodeURIComponent('Freejack'));
if (!response.ok) throw new Error('Crawler data is unavailable');
const { generated_at, games } = await response.json();
// Render games using textContent, not unsanitized innerHTML.
```

## Parser Improvements

XML discovery drains the trailing prompt, keeps every XML game even if a later
high-score check fails, and avoids replacing a previously XML-capable server's
games with an incomplete ANSI fallback when XML fails. `--missing` retries
incomplete crawls. Socket/protocol failures get one reconnect attempt. ANSI
escape sequences are processed across packet boundaries, and high scores retain
all pages separated by `[Pause]`.

Run regression tests with `PYTHONPATH=src python -m unittest discover -s tests -v`.
