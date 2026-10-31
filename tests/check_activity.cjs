// PLAYWRIGHT_MODULE can point to a temporary Playwright installation.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const path = require("node:path");

(async () => {
  const base = process.env.ACTIVITY_URL || "http://127.0.0.1:8022/active.html";
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(base);
    await page.locator("#main").waitFor({ state: "visible" });
    await page.locator("#run-select option:nth-child(2)").waitFor({ state: "attached" });
    assert.match(await page.locator("#snapshot-title").innerText(), /Run \d+/);
    await page.screenshot({ path: "/tmp/twcrawl-active-desktop.png", fullPage: true });
    await page.getByRole("tab", { name: "Online Players" }).click();
    await page.screenshot({ path: "/tmp/twcrawl-active-online.png", fullPage: true });
    await page.getByRole("tab", { name: "Find Games" }).click();
    await page.locator("#player-query").fill("Freejack");
    assert.ok(await page.locator("#search-results tbody tr").count() > 0);
    await page.screenshot({ path: "/tmp/twcrawl-active-search.png", fullPage: true });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      for (const name of ["Change Report", "Online Players", "Find Games", "Server Checks"]) {
        await page.getByRole("tab", { name }).click();
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Page overflows at ${width}: ${name}`);
      }
    }
    await page.getByRole("tab", { name: "Change Report" }).click();
    await page.screenshot({ path: "/tmp/twcrawl-active-mobile.png", fullPage: true });
    assert.deepEqual(errors, []);

    const generated = "2026-10-30T16:00:00+00:00";
    const game = { letter: "A", name: "SubZero", days_open: 45, bigbang: "09/15/2026", status: "ok", players: 2, sectors: 5000, time: "Unlimited", high_scores_checked_at: generated, high_scores: [{ name: "Freejack" }, { name: "<img src=x onerror=alert(1)>" }] };
    const server = { server_id: "1", name: "Test Server", telnet: "test:2002", status: "online", crawl_complete: true, games: [game], online_check: { status: "ok", checked_at: generated, players: [{ letter: "A", player: "Freejack" }] } };
    const session = { server_id: "1", server_name: "Test Server", server_telnet: "test:2002", letter: "A", player: "Freejack", checked_at: generated };
    const report = { generated_at: generated, previous_generated_at: "2026-10-29T16:00:00+00:00", summary: { game_count: 1, online_servers: 1 }, new_players: [{ ...session, player: { name: "<img src=x onerror=alert(1)>", rank: "1,234", alignment: "-100", ship_type: "Cruiser" } }], new_games: [{ ...session, game_name: "SubZero" }], newly_online: [session], activity: { session_count: 1, online_sessions: [session] }, failures: [] };
    const run = { id: 3, generated_at: generated, data: { servers: [server] }, report };
    let fail = false;
    await page.route("**/api/**", async route => {
      const url = new URL(route.request().url());
      if (fail) return route.fulfill({ status: 503, json: { error: "test failure" } });
      const payload = url.pathname === "/api/health" ? { run_id: 3 } : url.pathname === "/api/runs" ? { runs: [{ id: 3, generated_at: generated }, { id: 1, generated_at: generated, kind: "import" }], next_before: 1 } : { ...run, id: Number(url.pathname.split("/").pop()) };
      return route.fulfill({ json: payload });
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.reload();
    await page.locator("#main").waitFor({ state: "visible" });
    await page.locator("#run-select option:nth-child(2)").waitFor({ state: "attached" });
    assert.match(await page.locator("#new-players").innerText(), /<img src=x/);
    assert.equal(await page.locator("#new-players img").count(), 0);
    await page.locator("#run-select").selectOption("1");
    await page.waitForFunction(() => document.querySelector("#snapshot-title").textContent.includes("Run 1"));
    assert.equal(await page.locator("#run-select").inputValue(), "1");
    await page.getByRole("tab", { name: "Find Games" }).click();
    await page.locator("#player-query").fill("FREEJACK");
    assert.equal(await page.locator("#search-results tbody tr").count(), 1);
    await page.locator("#edit-query").fill("nomatch");
    assert.equal(await page.locator("#search-results tbody tr").count(), 0);
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#search-results tbody tr").length === 1);
    await page.locator('[data-sort="days"]').click();
    assert.equal(await page.locator('[data-sort="days"]').getAttribute("aria-sort"), "ascending");
    await page.locator('[data-sort="days"]').click();
    assert.equal(await page.locator('[data-sort="days"]').getAttribute("aria-sort"), "descending");
    fail = true;
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#load-status").textContent.includes("previously loaded"));
    assert.equal(await page.locator("#main").isVisible(), true);
    assert.deepEqual(errors, []);
    console.log("Activity page passed: live API, all views, 320/390px layouts, history, filters, sorting, escaped names and retained-error state.");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
