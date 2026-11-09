#!/usr/bin/env node
/**
 * Shell journeys on one or two production builds, at a desktop and a phone
 * viewport, in headless Chromium (Playwright; `require("playwright")`).
 *
 *   node scripts/qa-shell-journeys.mjs --build before=DIR [--build after=DIR] \
 *     --bundle FILE --bundle OTHER_FILE --out DIR
 *
 * Each build (`npm run build` output) is served locally. The journey loads
 * the first bundle with Open Existing, selects a region from the list, a
 * map node and a civilization chip, moves focus to the details and back,
 * rewinds with the turn slider's keys and a click on the track, opens the
 * compare dialog and cancels it with Escape (checking focus returns), Close
 * and the backdrop, then switches to the second bundle and back. At each
 * step it records the shell's DOM (stable over two frames, generated ids
 * normalised), its ARIA snapshot (landmarks, roles and names), the
 * landmark/role counts and, at the main steps, a screenshot; console
 * errors, warnings and page errors are collected per run. With two builds
 * it compares them step by step and exits non-zero on any difference, a
 * failed step or a console error. Screenshots and `report.json` go to
 * `--out`.
 */
import { loadPlaywright } from "./lib/playwright.mjs";
import { createServer } from "node:http";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json",
};

const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 } },
  mobile: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};

function parseArgs(argv) {
  const options = { builds: [], bundles: [], out: null };
  for (let index = 0; index < argv.length; index += 2) {
    const [flag, value] = [argv[index], argv[index + 1]];
    if (flag === "--build") {
      const at = value.indexOf("=");
      options.builds.push({ label: value.slice(0, at), path: path.resolve(value.slice(at + 1)) });
    } else if (flag === "--bundle") options.bundles.push(path.resolve(value));
    else if (flag === "--out") options.out = path.resolve(value);
    else throw new Error(`Unknown option ${flag}`);
  }
  if (options.builds.length < 1 || options.builds.length > 2 || options.bundles.length !== 2 || !options.out) {
    throw new Error("Usage: qa-shell-journeys.mjs --build a=DIR [--build b=DIR] --bundle FILE --bundle FILE --out DIR");
  }
  return options;
}

function serve(dir) {
  const root = path.resolve(dir);
  const server = createServer(async (request, response) => {
    try {
      let file = path.join(root, decodeURIComponent(new URL(request.url ?? "/", "http://x").pathname));
      if (file !== root && !file.startsWith(root + path.sep)) {
        response.writeHead(403).end();
        return;
      }
      if ((await stat(file)).isDirectory()) file = path.join(file, "index.html");
      response.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" });
      response.end(await readFile(file));
    } catch {
      response.writeHead(404).end();
    }
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** In the page: the shell's DOM once stable over two frames (no lazy placeholder), ids normalised. */
async function stableShell() {
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const read = () => (document.querySelector(".phase75-shell")?.outerHTML ?? "")
    .replace(/recharts\d+/g, "rechartsN")
    .replace(/«[^»]*»/g, "«id»")
    .replace(/_r_[0-9a-z]+_/g, "_r_id_")
    .replace(/:r[0-9a-z]+:/g, ":rid:");
  let previous = null;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await frame();
    await frame();
    const current = read();
    if (current === previous && !document.querySelector("[data-lazy-fallback]")) return current;
    previous = current;
  }
  return `UNSTABLE ${previous}`;
}

/** In the page: landmark and widget roles (explicit and implicit) with their counts. */
function roleCounts() {
  const implicit = { HEADER: "banner", NAV: "navigation", ASIDE: "complementary", MAIN: "main", FOOTER: "contentinfo" };
  const counts = {};
  for (const element of document.querySelectorAll(".phase75-shell *")) {
    let role = element.getAttribute("role") ?? implicit[element.tagName] ?? null;
    if (!role && element.tagName === "SECTION" && (element.getAttribute("aria-label") || element.getAttribute("aria-labelledby"))) role = "region";
    if (!role && element.tagName === "BUTTON") role = "button";
    if (!role && element.tagName === "SELECT") role = "combobox";
    if (role) counts[role] = (counts[role] ?? 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort(([a], [b]) => a.localeCompare(b)));
}

async function drive(browser, url, viewportName, bundles, outDir, buildLabel) {
  const context = await browser.newContext(VIEWPORTS[viewportName]);
  const page = await context.newPage();
  const messages = [];
  page.on("pageerror", (error) => messages.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") messages.push(`${message.type()}: ${message.text()}`);
  });
  const steps = [];
  const checks = [];
  const check = (name, ok, detail = "") => checks.push({ name, ok: !!ok, detail: String(detail) });
  const capture = async (name, screenshot = false) => {
    const html = await page.evaluate(stableShell);
    const aria = await page.locator(".phase75-shell").ariaSnapshot();
    const roles = await page.evaluate(roleCounts);
    let shot = null;
    if (screenshot) {
      shot = path.join(outDir, `${buildLabel}-${viewportName}-${name.replace(/[^a-z0-9]+/gi, "_")}.png`);
      await page.screenshot({ path: shot, fullPage: true, animations: "disabled", caret: "hide" });
    }
    steps.push({ name, html, aria, roles, screenshot: shot });
  };
  const playhead = () => page.locator(".phase75-playhead-label").textContent();
  const waitPlayhead = (text) => page.waitForFunction((value) => document.querySelector(".phase75-playhead-label")?.textContent === value,
    text, { timeout: 10000 });
  const waitWorld = (regions) => page.waitForFunction((count) => document.querySelector(".phase75-mode-tab.active")?.textContent === "Overview"
    && document.querySelectorAll(".phase75-region-node").length === count && !!document.querySelector(".phase75-playhead-label")
    && !document.querySelector("[data-lazy-fallback]") && !document.querySelector(".saved-world-loading"), regions, { timeout: 120000, polling: 50 });
  const inspectorRow = (label) => page.evaluate((wanted) => {
    const rows = [...document.querySelectorAll(".phase75-right-rail .phase75-stat-row")];
    return rows.find((row) => row.querySelector("span")?.textContent === wanted)?.querySelector("strong")?.textContent ?? "";
  }, label);
  const dialog = page.getByRole("dialog", { name: "Compare saved runs and reports" });
  const opener = page.getByRole("button", { name: "Compare saved runs", exact: true });
  const loader = page.getByLabel("Open saved world file");

  const [first, second] = await Promise.all(bundles.map(async (file) => JSON.parse(await readFile(file, "utf8"))));
  const regionsOf = (bundle) => bundle.world_state.regions.map((region) => region.name);

  await page.goto(url, { waitUntil: "load" });
  await page.waitForSelector(".phase75-shell");
  await capture("setup", true);

  // World load.
  await loader.setInputFiles(bundles[0]);
  await waitWorld(regionsOf(first).length);
  await capture("first world loaded", true);

  // Selection: region list, map node, civilization chip; focus to the details and back.
  const listed = regionsOf(first)[2];
  await page.getByRole("combobox", { name: "Inspect a region" }).selectOption(listed);
  check("region list selects", (await inspectorRow("Region")) === listed, await inspectorRow("Region"));
  const node = regionsOf(first)[1];
  await page.getByRole("button", { name: `Inspect region ${node}`, exact: true }).click();
  check("map node selects", (await inspectorRow("Region")) === node, await inspectorRow("Region"));
  const chip = page.locator(".phase75-civ-chip").first();
  const chipName = (await chip.textContent()) ?? "";
  await chip.click();
  check("civilization chip selects", (await inspectorRow("Civilization")) === chipName, `${chipName} / ${await inspectorRow("Civilization")}`);
  await capture("civilization selected", true);
  await page.getByRole("combobox", { name: "Inspect a region" }).selectOption(listed);
  await page.getByRole("button", { name: "View selection details" }).click();
  check("details take focus", await page.evaluate(() => document.activeElement?.id === "selected-world-details"));
  await page.getByRole("button", { name: "Back to map" }).click();
  check("map takes focus", await page.evaluate(() => document.activeElement?.id === "world-investigation-map"));

  // Rewind and scrub: slider keys, then a click on the track.
  const total = first.metadata.total_turns;
  const slider = page.getByRole("slider", { name: "Historical turn" });
  await slider.focus();
  await slider.press("End");
  await waitPlayhead(`T${total}`).then(() => check("End seeks the last turn", true), (error) => check("End seeks the last turn", false, error));
  await slider.press("PageDown");
  await waitPlayhead(`T${total - 10}`).then(() => check("PageDown rewinds ten turns", true), (error) => check("PageDown rewinds ten turns", false, error));
  await slider.press("Home");
  await waitPlayhead("T1").then(() => check("Home seeks turn 1", true), (error) => check("Home seeks turn 1", false, error));
  await slider.press("ArrowRight");
  await slider.press("ArrowRight");
  await waitPlayhead("T3").then(() => check("ArrowRight steps forward", true), (error) => check("ArrowRight steps forward", false, error));
  const box = await slider.boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const midTurn = Math.round(0.5 * (total - 1)) + 1;
  await waitPlayhead(`T${midTurn}`).then(() => check("track click seeks", true), (error) => check("track click seeks", false, error));
  check("selection kept through the rewind", (await inspectorRow("Region")) === listed, await inspectorRow("Region"));
  await capture("rewound", true);

  // Compare dialog: Escape (focus returns), Close, backdrop.
  await opener.focus();
  await opener.click();
  await dialog.waitFor();
  check("dialog takes focus", await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')));
  await capture("compare dialog open", true);
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "detached" });
  check("Escape returns focus to the opener", await page.evaluate(() => document.activeElement?.textContent === "Compare saved runs"));
  await opener.click();
  await dialog.waitFor();
  await dialog.locator(".phase75-modal-header").getByRole("button", { name: "Close" }).click();
  await dialog.waitFor({ state: "detached" });
  await opener.click();
  await dialog.waitFor();
  await page.locator(".phase75-modal-backdrop").click({ position: { x: 4, y: 4 } });
  await dialog.waitFor({ state: "detached" }).then(() => check("backdrop closes", true), (error) => check("backdrop closes", false, error));
  check("turn kept through the dialog", (await playhead()) === `T${midTurn}`, await playhead());
  await capture("dialog cancelled");

  // World switch and back.
  await loader.setInputFiles(bundles[1]);
  await waitWorld(regionsOf(second).length);
  check("second world has no first-world selection", (await inspectorRow("Region")) === "", await inspectorRow("Region"));
  await capture("second world loaded", true);
  await loader.setInputFiles(bundles[0]);
  await waitWorld(regionsOf(first).length);
  await capture("first world again", true);

  await context.close();
  return { steps, checks, messages };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const { chromium } = loadPlaywright();
  await mkdir(options.out, { recursive: true });
  const servers = await Promise.all(options.builds.map((build) => serve(build.path)));
  const urls = servers.map((server) => `http://127.0.0.1:${server.address().port}/`);
  const browser = await chromium.launch();
  const report = { generated: new Date().toISOString(), chromium: browser.version(),
    builds: options.builds.map((build) => build.label), bundles: options.bundles, viewports: {} };
  let failures = 0;
  try {
    for (const viewportName of Object.keys(VIEWPORTS)) {
      const runs = [];
      for (let index = 0; index < options.builds.length; index += 1) {
        runs.push(await drive(browser, urls[index], viewportName, options.bundles, options.out, options.builds[index].label));
      }
      const entry = { runs: runs.map((run, index) => ({
        build: options.builds[index].label,
        steps: run.steps.map((step) => ({ name: step.name, domBytes: step.html.length, unstable: step.html.startsWith("UNSTABLE"),
          roles: step.roles, screenshot: step.screenshot })),
        failedChecks: run.checks.filter((item) => !item.ok),
        checks: run.checks.length,
        consoleMessages: run.messages,
      })) };
      for (const run of entry.runs) failures += run.failedChecks.length + run.consoleMessages.length
        + run.steps.filter((step) => step.unstable).length;
      if (runs.length === 2) {
        const [left, right] = runs;
        const differences = [];
        for (let index = 0; index < Math.max(left.steps.length, right.steps.length); index += 1) {
          const [a, b] = [left.steps[index], right.steps[index]];
          if (!a || !b || a.name !== b.name) { differences.push({ step: a?.name ?? b?.name, what: "step" }); continue; }
          if (a.html !== b.html) differences.push({ step: a.name, what: "dom" });
          if (a.aria !== b.aria) differences.push({ step: a.name, what: "aria" });
          if (JSON.stringify(a.roles) !== JSON.stringify(b.roles)) differences.push({ step: a.name, what: "roles" });
          if (a.screenshot && b.screenshot && !(await readFile(a.screenshot)).equals(await readFile(b.screenshot))) {
            differences.push({ step: a.name, what: "screenshot" });
          }
        }
        entry.differences = differences;
        failures += differences.length;
      }
      report.viewports[viewportName] = entry;
      const summary = entry.runs.map((run) => `${run.build}: ${run.steps.length} steps, ${run.checks - run.failedChecks.length}/${run.checks} checks, `
        + `${run.consoleMessages.length} console messages`).join("; ");
      console.log(`${viewportName}: ${summary}${entry.differences ? `; ${entry.differences.length} differences` : ""}`);
      for (const run of entry.runs) for (const item of run.failedChecks) console.log(`   ${run.build} failed: ${item.name} ${item.detail}`);
      for (const run of entry.runs) for (const message of run.consoleMessages) console.log(`   ${run.build} console: ${message}`);
      for (const difference of entry.differences ?? []) console.log(`   differs: ${difference.step} (${difference.what})`);
    }
  } finally {
    await browser.close();
    for (const server of servers) server.close();
  }
  await writeFile(path.join(options.out, "report.json"), JSON.stringify(report, null, 2));
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
