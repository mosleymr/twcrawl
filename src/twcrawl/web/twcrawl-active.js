/* One immutable run supplies the report, rosters and online samples together. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const state = { run: null, games: [], servers: [], filter: "", view: "report", sort: "server", direction: 1, runs: [], next: null, request: 0 };
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const lower = value => String(value ?? "").toLocaleLowerCase();
  const number = value => value == null || value === "" || !Number.isFinite(Number(value)) ? "\u2014" : Number(value).toLocaleString();
  const date = value => {
    const parsed = new Date(value);
    return value && Number.isFinite(parsed.getTime()) ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "America/New_York" }).format(parsed) + " ET" : "Unknown";
  };
  const serverURL = id => `/games/server-${encodeURIComponent(id)}.html`;
  const gameURL = (id, letter) => `/games/server-${encodeURIComponent(id)}/game-${encodeURIComponent(lower(letter))}.html`;
  const key = (id, letter) => `${id}:${String(letter).toUpperCase()}`;
  const gameOf = row => state.games.find(g => key(g.server_id, g.letter) === key(row.server_id, row.letter));
  const destroyedShip = player => /^#\s*ship\s+destroyed\s*#$/i.test(String(player?.ship_type || "").trim());
  const roster = game => (game.high_scores || []).filter(player => !destroyedShip(player));
  const visibleSession = session => {
    if (destroyedShip(session)) return false;
    const players = (gameOf(session)?.high_scores || []).filter(player => lower(player.name).trim() === lower(session.player).trim());
    return !players.length || players.some(player => !destroyedShip(player));
  };
  const age = game => game?.days_open == null ? "Unknown age" : `${number(game.days_open)} days`;
  const linkServer = row => `<a href="${serverURL(row.server_id)}">${escape(row.server_name)}</a>`;
  const linkGame = row => {
    if (!row.letter) return "Server menu";
    const game = gameOf(row);
    const name = `${escape(row.letter)} &middot; ${escape(row.game_name || game?.name || `Game ${row.letter}`)}`;
    return game ? `<a href="${gameURL(row.server_id, row.letter)}">${name}</a>` : name;
  };
  const matches = row => !state.filter || lower(JSON.stringify([row, gameOf(row)?.name])).includes(state.filter);
  const table = (head, rows, empty) => rows.length ? `<div class="table-scroll"><table class="activity-table"><thead><tr>${head.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : `<p class="empty-state">${escape(empty)}</p>`;
  const rowGame = row => `<td>${linkServer(row)}</td><td>${linkGame(row)}<small>${escape(age(gameOf(row)))}</small></td>`;
  const report = () => state.run.report || state.run.data.latest_report || {};
  const activity = () => report().activity || { online_sessions: [], server_checks: [] };
  const onlineSessions = () => (activity().online_sessions || []).filter(visibleSession);
  const status = (message, error = false) => { $("load-status").textContent = message; $("load-status").dataset.error = String(error); };
  async function request(path) {
    const response = await fetch(`/api${path}`, { cache: "no-store", signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error(`API returned ${response.status}`);
    return response.json();
  }
  function flatten(data) {
    return (data.servers || []).flatMap(s => (s.games || []).map(g => ({ ...g, server_id: s.server_id, server_name: s.name, server_telnet: s.telnet, server_status: s.status, crawl_complete: s.crawl_complete })));
  }
  function renderHeader() {
    const r = report(), summary = r.summary || {};
    const failed = (r.failures || []).length;
    const partial = state.servers.filter(s => s.status === "online" && s.crawl_complete === false).length;
    $("snapshot-title").textContent = `${$("run-select").value === "latest" ? "Latest Crawl" : "Archived Crawl"} / Run ${state.run.id}`;
    $("snapshot-time").textContent = date(state.run.generated_at);
    $("comparison").textContent = r.previous_generated_at ? `Compared with ${date(r.previous_generated_at)}. ${partial} incomplete server${partial === 1 ? "" : "s"}; ${failed} failed check${failed === 1 ? "" : "s"}.` : "Baseline snapshot. Change comparisons start with subsequent crawls.";
    const metrics = [[summary.online_servers ?? state.servers.filter(s => s.status === "online").length, `of ${state.servers.length} server records reached`, ""], [summary.game_count ?? state.games.length, "Distinct games known", ""], [onlineSessions().length, "Online sessions listed", "positive"], [(r.new_players || []).length, "New player records", "positive"], [failed, "Failed server checks", failed ? "warning" : ""]];
    $("metrics").innerHTML = metrics.map(([n, label, cls]) => `<div class="metric"><strong class="${cls}">${number(n)}</strong><span>${escape(label)}</span></div>`).join("");
    $("json-link").href = `/api/runs/${state.run.id}/report`;
    const selected = $("server-query").value;
    $("server-query").innerHTML = '<option value="">All servers</option>' + state.servers.slice().sort((a, b) => a.name.localeCompare(b.name)).map(s => `<option value="${escape(s.server_id)}">${escape(s.name)}</option>`).join("");
    $("server-query").value = selected;
  }
  function renderReport() {
    const r = report();
    const players = (r.new_players || []).filter(matches);
    $("new-players-count").textContent = `${players.length} record${players.length === 1 ? "" : "s"}`;
    $("new-players").innerHTML = table(["Player", "Server", "Game / Age", "Rank", "Alignment", "Ship Type"], players.map(p => `<tr><td class="good">${escape(p.player?.name)}</td>${rowGame(p)}<td class="num">${escape(p.player?.rank ?? "Unknown")}</td><td class="num">${escape(p.player?.alignment ?? "Unknown")}</td><td>${escape(p.player?.ship_type || "Unknown")}</td></tr>`), state.filter ? "No matching new player records." : "No newly seen player records in this comparison.");
    const changes = [["Newly observed", "new_games", "good"], ["Rebanged", "rebanged_games", "warn"], ["Removed", "removed_games", "bad"]].flatMap(([label, field, cls]) => (r[field] || []).map(row => ({ ...row, label, cls }))).filter(matches);
    $("game-changes-count").textContent = `${changes.length} changes`;
    $("game-changes").innerHTML = table(["Change", "Server", "Game / Age", "BigBang", "Previous BigBang"], changes.map(g => `<tr><td class="${g.cls}">${g.label}</td>${rowGame(g)}<td>${escape(g.bigbang || "Unknown")}</td><td>${escape(g.previous_bigbang || "\u2014")}</td></tr>`), "No matching new, removed or rebanged games.");
    const presence = [["Newly sampled online", "newly_online", "good"], ["No longer sampled", "no_longer_online", "warn"]].flatMap(([label, field, cls]) => (r[field] || []).map(row => ({ ...row, label, cls }))).filter(visibleSession).filter(matches);
    $("presence-count").textContent = `${presence.length} changes`;
    $("presence-changes").innerHTML = table(["Observation", "Player", "Server", "Game / Age", "Sample Time"], presence.map(p => `<tr><td class="${p.cls}">${p.label}</td><td>${escape(p.player)}</td>${rowGame(p)}<td>${escape(date(p.checked_at))}</td></tr>`), "No matching online presence changes.");
  }
  function renderOnline() {
    const sessions = onlineSessions().filter(matches);
    $("online-count").textContent = `${sessions.length} sessions / ${new Set(sessions.map(s => lower(s.player))).size} players`;
    const servers = new Map();
    for (const session of sessions) {
      const k = String(session.server_id);
      if (!servers.has(k)) servers.set(k, { sample: session, games: new Map() });
      const groups = servers.get(k).games;
      const letter = session.letter || "Menu";
      if (!groups.has(letter)) groups.set(letter, []);
      groups.get(letter).push(session);
    }
    $("online-groups").innerHTML = [...servers.values()].sort((a, b) => a.sample.server_name.localeCompare(b.sample.server_name)).map(({ sample, games }) => `<div class="online-server"><h3>${linkServer(sample)}</h3><p>${escape(sample.server_telnet)} &middot; Checked ${escape(date(sample.checked_at))}</p>${[...games.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, rows]) => `<div class="online-game"><div>${linkGame(rows[0])}</div><div class="player-names">${rows.map(p => escape(p.player)).join(" &middot; ")}</div><div class="age">${rows[0].letter ? escape(age(gameOf(rows[0]))) : ""}</div></div>`).join("")}</div>`).join("") || '<p class="empty-state">No matching online sessions in the successful samples.</p>';
  }
  function renderChecks() {
    const rows = state.servers.map(s => ({ ...s, server_id: s.server_id, server_name: s.name })).filter(matches).sort((a, b) => (a.status === "online") - (b.status === "online") || a.name.localeCompare(b.name));
    $("checks-count").textContent = `${rows.length} server records`;
    $("server-checks").innerHTML = table(["Server", "Crawl", "Games", "Online Check", "Checked", "Details"], rows.map(s => {
      const partial = s.crawl_complete === false;
      const label = s.status !== "online" ? "Failed" : partial ? "Incomplete" : "Reached";
      const check = s.online_check || {};
      const detail = s.error || (partial ? "Some game data or high scores are incomplete." : "");
      const sessions = (check.players || []).filter(p => visibleSession({ ...p, server_id: s.server_id }));
      return `<tr><td>${linkServer(s)}<small>${escape(s.telnet)}</small></td><td class="${s.status !== "online" ? "bad" : partial ? "warn" : "good"}">${label}</td><td class="num">${number(s.games?.length || 0)}</td><td class="${check.status === "ok" ? "good" : "warn"}">${check.status === "ok" ? `${sessions.length} listed` : "Unknown"}</td><td>${escape(date(check.checked_at || s.last_crawled_at))}</td><td>${escape(detail || "\u2014")}</td></tr>`;
    }), "No matching server checks.");
  }
  const fresh = g => g.server_status === "online" && ["ok", "closed"].includes(g.status);
  function renderSearch() {
    const player = lower($("player-query").value.trim()), edit = lower($("edit-query").value.trim());
    const selected = $("server-query").value, records = $("record-query").value;
    let games = state.games.filter(g => (!selected || String(g.server_id) === selected) && (!player || roster(g).some(p => lower(p.name).includes(player))) && (!edit || lower(JSON.stringify([g.name, g.stats, g.raw_stats, g.xml])).includes(edit)) && (records === "all" || (records === "fresh" ? fresh(g) : !fresh(g))));
    const sortValue = g => ({ server: `${g.server_name} ${g.letter}`, name: g.name || "", days: Number(g.days_open ?? -1), players: Number(g.players ?? -1), sectors: Number(g.sectors ?? -1), bigbang: Date.parse(g.bigbang || "") || 0, time: g.time || "" })[state.sort];
    games.sort((a, b) => {
      const x = sortValue(a), y = sortValue(b);
      return state.direction * (typeof x === "number" ? x - y : String(x).localeCompare(String(y)));
    });
    $("search-count").textContent = `${games.length} game records`;
    const headings = [["server", "Server"], ["name", "Game"], ["bigbang", "BigBang"], ["days", "Days"], ["players", "Players"], [null, "Roster / Online"], ["sectors", "Sectors"], ["time", "Time Limit"], [null, "Data"]].map(([key, label]) => key ? `<button class="sort-column" type="button" data-sort="${key}" aria-sort="${state.sort === key ? (state.direction === 1 ? "ascending" : "descending") : "none"}">${label}</button>` : label);
    $("search-results").innerHTML = table(headings, games.map(g => {
      const names = roster(g).map(p => p.name).filter(Boolean);
      const highlighted = player ? names.filter(n => lower(n).includes(player)) : names.slice(0, 4);
      const remainder = names.filter(n => !highlighted.includes(n));
      const online = onlineSessions().filter(p => key(p.server_id, p.letter) === key(g.server_id, g.letter)).map(p => p.player);
      const days = g.days_open;
      return `<tr><td>${linkServer(g)}</td><td>${linkGame(g)}</td><td>${escape(g.bigbang || "Unknown")}</td><td class="num ${days == null ? "muted" : days < 60 ? "good" : days <= 120 ? "warn" : "bad"}">${number(days)}</td><td class="num">${number(g.players)}</td><td class="names">${highlighted.map(escape).join(", ") || (g.high_scores_checked_at ? "No eligible roster entries" : "No captured roster")}${remainder.length ? `<details><summary>${remainder.length} more</summary>${remainder.map(escape).join(", ")}</details>` : ""}<small class="good">${online.length ? `Online: ${online.map(escape).join(", ")}` : ""}</small></td><td class="num">${number(g.sectors)}</td><td class="${lower(g.time) === "unlimited" ? "good" : "bad"}">${escape(g.time || "Unknown")}</td><td class="${fresh(g) ? "good" : "warn"}">${fresh(g) ? "Captured" : g.server_status !== "online" ? "Retained" : "Partial"}<small>${g.high_scores_error ? "High scores unavailable" : g.high_scores_checked_at ? "Roster checked" : "No roster check"}</small></td></tr>`;
    }), "No games match these filters.");
  }
  function render() { renderHeader(); renderReport(); renderOnline(); renderChecks(); renderSearch(); }
  function showView(view) {
    state.view = view;
    document.querySelectorAll("[data-view]").forEach(b => { b.setAttribute("aria-selected", String(b.dataset.view === view)); b.tabIndex = b.dataset.view === view ? 0 : -1; });
    for (const name of ["report", "online", "search", "checks"]) $(`view-${name}`).hidden = name !== view;
    $("activity-filter-wrap").hidden = view === "search";
  }
  function renderRunOptions() {
    const selected = $("run-select").value;
    $("run-select").innerHTML = '<option value="latest">Latest completed crawl</option>' + state.runs.map(r => `<option value="${r.id}">Run ${r.id} / ${escape(date(r.generated_at))}${r.kind === "import" ? " / Baseline" : ""}</option>`).join("");
    $("run-select").value = selected;
    $("older-button").hidden = !state.next || state.runs.length < 50;
  }
  async function loadRuns(before) {
    const result = await request(`/runs?limit=50${before ? `&before=${before}` : ""}`);
    state.runs = before ? [...state.runs, ...result.runs] : result.runs;
    state.next = result.next_before;
    renderRunOptions();
  }
  async function load() {
    const requestId = ++state.request;
    $("refresh-button").disabled = true;
    status(state.run ? "Checking stored crawl..." : "Loading stored crawl...");
    try {
      const selected = $("run-select").value;
      const id = selected === "latest" ? (await request("/health")).run_id : Number(selected);
      if (!Number.isSafeInteger(id) || id < 1) throw new Error("No archived crawl is available yet");
      const run = await request(`/runs/${id}`);
      if (requestId !== state.request) return;
      if (!Array.isArray(run.data?.servers)) throw new Error("The stored snapshot is incomplete");
      state.run = run; state.servers = run.data.servers; state.games = flatten(run.data);
      render(); $("main").hidden = false;
      const hoursOld = (Date.now() - new Date(run.generated_at).getTime()) / 3600000;
      status(selected === "latest" && hoursOld > 14 ? "The latest stored crawl is more than 14 hours old. Online observations are historical samples." : "Stored crawl loaded. Online observations carry their own sample times.", selected === "latest" && hoursOld > 14);
      $("checked-time").textContent = `Page checked ${date(new Date().toISOString())}`;
      try { if (selected === "latest" || !state.runs.length) await loadRuns(); } catch { status("Report loaded; crawl history is temporarily unavailable.", true); }
    } catch (error) {
      if (requestId === state.request) status(`${state.run ? "Showing the previously loaded snapshot. " : ""}Unable to load crawler data: ${error.message}.`, true);
    } finally { if (requestId === state.request) $("refresh-button").disabled = false; }
  }
  document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelector(".view-tabs").addEventListener("keydown", event => {
    const tabs = [...document.querySelectorAll("[data-view]")];
    let index = tabs.indexOf(document.activeElement);
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[index].click(); tabs[index].focus();
  });
  $("activity-filter").addEventListener("input", () => { state.filter = lower($("activity-filter").value.trim()); if (state.run) { renderReport(); renderOnline(); renderChecks(); } });
  $("game-search").addEventListener("submit", e => e.preventDefault());
  $("game-search").addEventListener("input", () => state.run && renderSearch());
  $("game-search").addEventListener("change", () => state.run && renderSearch());
  $("game-search").addEventListener("reset", () => setTimeout(() => state.run && renderSearch(), 0));
  $("search-results").addEventListener("click", e => { const button = e.target.closest("[data-sort]"); if (!button) return; state.direction = state.sort === button.dataset.sort ? -state.direction : 1; state.sort = button.dataset.sort; renderSearch(); });
  $("refresh-button").addEventListener("click", load);
  $("run-select").addEventListener("change", load);
  $("older-button").addEventListener("click", async () => { try { await loadRuns(state.next); } catch (e) { status(`Unable to load earlier crawls: ${e.message}`, true); } });
  setInterval(() => { if ($("auto-refresh").checked && $("run-select").value === "latest" && !document.hidden && !$("refresh-button").disabled) load(); }, 300000);
  load();
})();
