# twcrawl design

## Goal

Replicate the MicroBlaster server crawler/bot function for TWGS servers:

- Maintain a seed list of known TradeWars servers.
- Crawl each telnet endpoint with the bot name `twcrawl`.
- Enumerate game letters from the TWGS server menu.
- Enter each game, acknowledge optional `[Pause]`, request `*` game stats,
  capture the structured output, request `H` high scores, capture active-player
  rows, exit the game, and continue.
- Persist the result as JSON.
- Generate static MicroBlaster-style `servers.aspx` and server-detail pages.

## Components

- `twcrawl.importer`: imports the archived MicroBlaster TWGS2 server table into
  `data/servers.seed.json`.
- `twcrawl.crawler.add_server`: local server-list upsert helper used by
  `twcrawl add-server`.
- `twcrawl.telnet`: small RFC 854 telnet client with TWGS-compatible initial
  handshake, terminal-type response, NAWS response, and ANSI/CP437 cleaning.
- `twcrawl.crawler`: TWGS menu state machine and JSON persistence.
- `twcrawl.parser`: server menu parser plus `Game Stats` key/value parser.
- `twcrawl.render`: static HTML/CSS generator for the server list and one
  detail page per server.
- `twcrawl.history`: timestamped crawl snapshot storage for scheduled runs.
- `twcrawl.search`: flattened game search by game/edit/config text and player.
- `twcrawl.mtc_monitor`: recent MTC game config scanner, high-score delta
  monitor, and live `#` online checker.
- `twcrawl.cli`: command line interface.

## Data model

The runtime JSON is stored at `data/twcrawl.json`:

```json
{
  "generated_at": "2026-06-30T09:39:00+00:00",
  "servers": [
    {
      "server_id": "364",
      "name": "Gone Rogue",
      "telnet": "roguetw.net:2002",
      "status": "online",
      "last_bigbang": "05/28/2026",
      "tradewars_version": "TWGS 2.20b",
      "game_count": 12,
      "players": 33,
      "games": [
        {
          "letter": "A",
          "name": "Dragon Slayer",
          "bigbang": "02/13/2026",
          "days_open": 136,
          "type": "Open",
          "version": "3.34GM",
          "emulation": "1 Mps",
          "time": "480 Min",
          "turns": "25000 Turns",
          "sectors": 20000,
          "players": 1,
          "high_scores": [
            {
              "position": 1,
              "rank": "10,616",
              "rank_value": 10616,
              "alignment": "3,077",
              "alignment_value": 3077,
              "corp": "**",
              "name": "chewbacca",
              "ship_type": "Imperial StarShip"
            }
          ],
          "raw_high_scores": "Ranking Traders...\nTrade Wars 2002 Trader Rankings..."
        }
      ]
    }
  ]
}
```

## Adding servers

`twcrawl add-server HOST PORT NAME` adds or updates a server using only the
connection endpoint and display name:

```bash
twcrawl add-server games.opentw.org 2002 OpenTW
twcrawl add-server games.example.net 2002 My TWGS
```

The command writes the active data file (`data/twcrawl.json`) and, unless
`--no-seeds` is supplied, also writes the local seed file
(`data/servers.seed.json`). The command generates a stable slug/server id from
the display name for new servers, updates an existing row when the telnet
endpoint, slug, or name already exists, and resets crawl status only when an
existing row's endpoint changes.

Use `--crawl --build` to immediately crawl the new server and rebuild the
static site/API.

## Crawl state machine

1. Connect to `host:port`.
2. Send initial telnet handshake `IAC DO 246`.
3. Respond to telnet options:
   - `DO TERMINAL-TYPE` -> `WILL TERMINAL-TYPE`, then subnegotiation `ANSI`.
   - `DO NAWS` -> `WILL NAWS`, then `80x25`.
   - `DO SUPPRESS-GA` -> `WILL SUPPRESS-GA`.
   - Unsupported options are refused.
4. Wait for `Please enter your name`.
5. Send `twcrawl`.
6. Wait until the server menu contains parseable `<A> Game Name` entries and
   any menu prompt ending in `: ` or `? `. This handles both normal TWGS
   `Selection (? for menu):` menus and customized menus such as
   `Select a game :`. If a customized ANSI menu displays game letters and then
   waits for input without printing any prompt, treat the menu as ready after
   output goes quiet briefly.
7. Parse game entries from the server menu, including both `<A> Game Name`
   and customized `A. Game Name` formats. Adjacent entries such as
   `A. First GameB. Second Game` are supported. Ignore non-game commands such
   as `<Q>`.
8. For each game:
   - Send the game letter.
   - Wait for `Enter your choice:`.
   - If `[Pause]` appears, send Enter and keep waiting.
   - Send `*`.
   - Capture from `Game Stats:` through `End Stats.`.
   - Parse the key/value stats.
   - Send `H`.
   - Acknowledge any `[Pause]` prompts.
   - Capture and parse the high-score rows into `high_scores`.
   - Send `X` and wait for the server menu.
9. Send `Q` and close.

## Derived fields

- `players`: highest `Active Players` count among the crawled games.
- `last_bigbang`: latest game `Start Day`.
- `version`: `Major.Minor`, plus `G` when `Gold Enabled=True`, plus `M` when
  `MBBS Compatibility=True`.
- `type`: `Open` unless `Closed Game=True`.
- `bigbang`: TWGS game dates are normalized from the in-game year to the crawl
  timestamp year by matching `Local Game Time`.

## Player lookup API

`twcrawl build` generates a player lookup API from each game's `high_scores`
rows. This is intended for clients such as MTC and is not linked from the
generated HTML pages.

Static Apache files:

```text
/api/players.json
/api/players/{player_slug}.json
/api/players/{player_slug}/games.json
```

`twcrawl serve` also supports:

```text
/api/games?player=chewbacca
/api/configurations?player=chewbacca
/api/players
/api/players/chewbacca
/api/players/chewbacca/games
```

Player slugs are generated from the active-player names in high scores. The
`player=` query parameter is a case-insensitive substring match.

## Live player online checks

`twcrawl online PLAYER` is a probe command, not part of the static API. It uses
the generated player index to limit work to servers where the player has known
high-score entries, connects to each of those servers once, logs in as the bot,
sends `#` at the TWGS server menu, and parses the `Players Online` node list.

The command compares live player locations against the known games for that
player on each server and reports:

- games where the player is currently logged in;
- known games on that server where the player is not currently logged in;
- server-level online locations that could not be mapped to a game, such as
  the TWGS menu.

## Daily history

`twcrawl daily` is the scheduler-oriented command. It runs the normal crawler,
writes `data/twcrawl.json`, rebuilds the public site by default, and stores a
timestamped full JSON snapshot in `data/history/`. `latest.json` is maintained
as a copy of the newest snapshot, and `manifest.json` lists snapshots.

Runtime history is ignored by git because deployments should not overwrite
crawler data on pull.

## Search command

`twcrawl search` reads `data/twcrawl.json` and searches flattened game rows.
The positional query and `--edit` search server identity, game name, original
menu name, summary fields, and parsed `*` stats keys/values. `--player` filters
by active-player high-score name substring. `--json` returns the same full game
records used by API clients.

## MTC recent-game monitor

`twcrawl monitor-mtc` scans MTC game config JSON files under
`/Users/mosleym/twx/games` that were modified within a configurable window
(`--days`, default 60). It uses each config's `Host`, `Port`, and `GameLetter`
to find the matching twcrawl server/game, then:

- compares current high-score names with the previous monitor state;
- reports newly seen players after the first baseline run;
- sends `#` once per matched server to list currently online players;
- maps online locations back to the monitored game letters.

Monitor state is stored under `data/monitors/`, which is ignored by git:

```text
data/monitors/mtc-recent.json
data/monitors/mtc-recent-last-report.json
```
