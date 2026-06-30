# twcrawl

`twcrawl` is a standalone TradeWars Game Server crawler that recreates the
defunct MicroBlaster server-list workflow:

1. Read a JSON seed list of known TWGS servers.
2. Open a telnet connection to each server.
3. Login with the crawler name, enumerate the game letters from the TWGS menu,
   enter each game, press `*` at `Enter your choice:`, capture `Game Stats`,
   exit, and continue.
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
twcrawl crawl --all --build
twcrawl crawl --only "Gone Rogue" --build
twcrawl build
twcrawl serve --port 8008
```

The same commands can also be run as a Python module on any platform:

```bash
python -m twcrawl init-seeds
python -m twcrawl crawl --all --build
python -m twcrawl serve --port 8008
```

By default the crawler stores state in `data/twcrawl.json` and generates pages
under `public/`.

## Notes

- The crawler and web server are cross-platform Python code. They use only the
  Python standard library plus the package metadata in `pyproject.toml`.
- TWGS expects real telnet negotiation. `twcrawl` sends the same initial telnet
  handshake style used by TWX/MTC and responds to terminal type, NAWS, and
  suppress-go-ahead options.
- Game version display follows MicroBlaster convention: `Major.Minor` plus `G`
  for Gold Enabled and `M` for MBBS Compatibility.
- TWGS `mm/dd/yy` dates use the in-game year. The crawler maps the local game
  year from `Local Game Time` to the crawl timestamp year, so current servers
  render as normal calendar years.
