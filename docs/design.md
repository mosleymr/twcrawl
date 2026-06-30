# twcrawl design

## Goal

Replicate the MicroBlaster server crawler/bot function for TWGS servers:

- Maintain a seed list of known TradeWars servers.
- Crawl each telnet endpoint with the bot name `twcrawl`.
- Enumerate game letters from the TWGS server menu.
- Enter each game, acknowledge optional `[Pause]`, request `*` game stats,
  capture the structured output, exit the game, and continue.
- Persist the result as JSON.
- Generate static MicroBlaster-style `servers.aspx` and server-detail pages.

## Components

- `twcrawl.importer`: imports the archived MicroBlaster TWGS2 server table into
  `data/servers.seed.json`.
- `twcrawl.telnet`: small RFC 854 telnet client with TWGS-compatible initial
  handshake, terminal-type response, NAWS response, and ANSI/CP437 cleaning.
- `twcrawl.crawler`: TWGS menu state machine and JSON persistence.
- `twcrawl.parser`: server menu parser plus `Game Stats` key/value parser.
- `twcrawl.render`: static HTML/CSS generator for the server list and one
  detail page per server.
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
          "players": 1
        }
      ]
    }
  ]
}
```

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
