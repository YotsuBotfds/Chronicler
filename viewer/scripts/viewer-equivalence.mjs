#!/usr/bin/env node
/**
 * Rendered-DOM equivalence of two viewer builds on the same bundles
 * (docs/performance/viewer-2026-10.md).
 *
 *   node scripts/viewer-equivalence.mjs --build main=DIR --build branch=DIR \
 *     --bundle guard=FILE --bundle proc32=FILE --out report.json
 *
 * Each build (`npm run build` output) is served locally and driven in
 * headless Chromium (Playwright) through the same sequence: upload the
 * bundle, then at a set of turns (the first ones, quarters, the last ones
 * and seeded random turns) capture the whole shell's DOM on the overview;
 * each systems tab, each map layer, the Event Log, a pinned event (before,
 * at and after its turn), two selected regions, the Character, Trade and
 * Campaign surfaces and the region history inspector at a subset of turns.
 * A capture is the shell's outerHTML once it is stable over two frames,
 * with generated ids (Recharts clip paths, React ids) normalised; a lazy
 * panel's loading placeholder must be gone. The script compares the
 * captures pairwise and exits non-zero on any difference.
 */
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const require = createRequire(import.meta.url);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json",
};

function parseArgs(argv) {
  const options = { builds: [], bundles: [], out: null, seed: 20261026, random: 4 };
  for (let index = 0; index < argv.length; index += 2) {
    const [flag, value] = [argv[index], argv[index + 1]];
    const pair = () => {
      const at = value.indexOf("=");
      return { label: value.slice(0, at), path: path.resolve(value.slice(at + 1)) };
    };
    if (flag === "--build") options.builds.push(pair());
    else if (flag === "--bundle") options.bundles.push(pair());
    else if (flag === "--out") options.out = path.resolve(value);
    else if (flag === "--random") options.random = Number(value);
    else throw new Error(`Unknown option ${flag}`);
  }
  if (options.builds.length !== 2 || options.bundles.length === 0) {
    throw new Error("Usage: viewer-equivalence.mjs --build a=DIR --build b=DIR --bundle label=FILE [--out FILE]");
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

function lcg(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

/** In the page: the shell's DOM once stable over two frames, ids normalised. */
async function captureInPage() {
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const read = () => (document.querySelector(".phase75-shell")?.outerHTML ?? "")
    .replace(/recharts\d+/g, "rechartsN")
    .replace(/«[^»]*»/g, "«id»")
    .replace(/_r_[0-9a-z]+_/g, "_r_id_")
    .replace(/:r[0-9a-z]+:/g, ":rid:");
  let previous = null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await frame();
    await frame();
    const current = read();
    if (current === previous && !document.querySelector("[data-lazy-fallback]")) {
      return current;
    }
    previous = current;
  }
  return `UNSTABLE ${previous}`;
}

async function seekInPage({ turn, total }) {
  const track = document.querySelector(".phase75-turn-track");
  const rect = track.getBoundingClientRect();
  const x = rect.left + ((turn - 1) / Math.max(total - 1, 1)) * rect.width;
  track.dispatchEvent(new MouseEvent("click", {
    bubbles: true, cancelable: true, view: window, clientX: x, clientY: rect.top + rect.height / 2,
  }));
  for (let attempt = 0; attempt < 500; attempt += 1) {
    if (document.querySelector(".phase75-playhead-label")?.textContent === `T${turn}`) return true;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  return false;
}

async function drive(browser, url, bundle, total, turns, subset) {
  const context = await browser.newContext({ viewport: { width: 1920, height: 1200 } });
  const page = await context.newPage();
  const messages = [];
  let workers = 0;
  page.on("worker", () => { workers += 1; });
  page.on("pageerror", (error) => messages.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") messages.push(`${message.type()}: ${message.text()}`);
  });
  await page.goto(url, { waitUntil: "load" });
  await page.waitForSelector(".phase75-shell");
  await page.locator('input[type="file"][accept=".json"]').first().setInputFiles(bundle.path);
  await page.waitForFunction(() => document.querySelector(".phase75-mode-tab.active")?.textContent === "Overview"
    && !!document.querySelector(".phase75-playhead-label") && !document.querySelector("[data-lazy-fallback]"),
  null, { timeout: 120000, polling: 50 });

  const captures = [];
  const capture = async (state, turn) => {
    if (!(await page.evaluate(seekInPage, { turn, total }))) {
      captures.push({ state, turn, html: "SEEK FAILED" });
      return;
    }
    captures.push({ state, turn, html: await page.evaluate(captureInPage) });
  };
  const click = async (locator) => {
    await locator.click();
    await page.evaluate(captureInPage);
  };

  for (const turn of turns) await capture("overview", turn);

  const systemTabs = page.getByRole("tablist", { name: "Simulation systems" }).getByRole("tab");
  const tabNames = await systemTabs.allTextContents();
  for (const name of tabNames) {
    await click(page.getByRole("tablist", { name: "Simulation systems" }).getByRole("tab", { name, exact: true }));
    for (const turn of subset) await capture(`systems:${name}`, turn);
  }

  const layerNames = await page.getByRole("radiogroup", { name: "Map layer" }).getByRole("radio").allTextContents()
    .catch(() => []);
  for (const name of layerNames) {
    await click(page.getByRole("radiogroup", { name: "Map layer" }).getByRole("radio", { name, exact: true }));
    for (const turn of subset) await capture(`layer:${name}`, turn);
  }
  if (layerNames.length) {
    await click(page.getByRole("radiogroup", { name: "Map layer" }).getByRole("radio", { name: "Control", exact: true }));
  }

  await click(page.getByRole("button", { name: "Event Log", exact: true }));
  for (const turn of subset) await capture("events", turn);
  // Pin the first listed event at the middle turn, then look before, at and after its turn.
  await page.evaluate(seekInPage, { turn: subset[1], total });
  const row = page.locator(".phase75-event-row").first();
  if (await row.count()) {
    const pinnedTurn = Number((await row.locator(".phase75-event-turn").textContent())?.slice(1));
    await click(row);
    for (const turn of [...new Set([1, Math.max(1, pinnedTurn - 1), pinnedTurn, Math.min(total, pinnedTurn + 1), total])]) {
      await capture("pinned-event", turn);
    }
  }

  const regions = page.locator(".phase75-region-node");
  const regionCount = await regions.count();
  for (const index of [0, Math.floor(regionCount / 2)]) {
    await click(regions.nth(index));
    for (const turn of subset) await capture(`region:${index}`, turn);
  }

  for (const surface of ["Character", "Trade", "Campaign"]) {
    await click(page.getByRole("button", { name: surface, exact: true }));
    for (const turn of subset) await capture(`surface:${surface}`, turn);
  }

  await click(page.getByRole("button", { name: "Overview", exact: true }));
  await click(page.getByText("Inspect region history", { exact: true }));
  for (const turn of subset) await capture("region-history", turn);

  const decoded = await page.evaluate(() => performance.getEntriesByName("chronicler:bundle-decoded").length > 0);
  await context.close();
  return { captures, messages, workers, decodedInWorker: decoded };
}

function firstDifference(left, right) {
  let index = 0;
  while (index < left.length && index < right.length && left[index] === right[index]) index += 1;
  return { index, left: left.slice(Math.max(0, index - 120), index + 200), right: right.slice(Math.max(0, index - 120), index + 200) };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const { chromium } = require("playwright");
  const servers = [];
  const urls = [];
  for (const build of options.builds) {
    const server = await serve(build.path);
    servers.push(server);
    urls.push(`http://127.0.0.1:${server.address().port}/`);
  }
  const browser = await chromium.launch();
  const report = { generated: new Date().toISOString(), chromium: browser.version(), builds: options.builds.map((b) => b.label),
    bundles: [] };
  let differences = 0;
  try {
    for (const bundle of options.bundles) {
      const parsed = JSON.parse(await readFile(bundle.path, "utf8"));
      const total = parsed.metadata?.total_turns ?? (parsed.history_delta ?? parsed.history).length;
      const next = lcg(options.seed);
      const random = Array.from({ length: options.random }, () => 1 + Math.floor(next() * total));
      const turns = [...new Set([1, 2, 3, Math.floor(total / 4), Math.floor(total / 2) + 1, Math.floor((3 * total) / 4),
        total - 1, total, ...random])].filter((turn) => turn >= 1 && turn <= total).sort((a, b) => a - b);
      const subset = [...new Set([1, Math.floor(total / 2) + 1, total])];
      const runs = [];
      for (let index = 0; index < 2; index += 1) {
        runs.push(await drive(browser, urls[index], bundle, total, turns, subset));
      }
      const [left, right] = runs;
      const mismatches = [];
      if (left.captures.length !== right.captures.length) {
        mismatches.push({ state: "capture count", detail: `${left.captures.length} vs ${right.captures.length}` });
      }
      for (let index = 0; index < Math.min(left.captures.length, right.captures.length); index += 1) {
        const [a, b] = [left.captures[index], right.captures[index]];
        if (a.state !== b.state || a.turn !== b.turn || a.html !== b.html
            || a.html.startsWith("UNSTABLE") || a.html === "SEEK FAILED") {
          mismatches.push({ state: `${a.state}@${a.turn}`, other: `${b.state}@${b.turn}`, ...firstDifference(a.html, b.html) });
        }
      }
      differences += mismatches.length;
      const entry = {
        bundle: bundle.label, turns: total, sampledTurns: turns, subset, captures: left.captures.length,
        states: [...new Set(left.captures.map((c) => c.state))],
        bytesCompared: left.captures.reduce((sum, c) => sum + c.html.length, 0),
        mismatches,
        consoleMessages: { [options.builds[0].label]: left.messages, [options.builds[1].label]: right.messages },
        workers: { [options.builds[0].label]: left.workers, [options.builds[1].label]: right.workers },
        decodedInWorker: { [options.builds[0].label]: left.decodedInWorker, [options.builds[1].label]: right.decodedInWorker },
      };
      report.bundles.push(entry);
      console.log(`${bundle.label}: ${entry.captures} captures in ${entry.states.length} states, `
        + `${(entry.bytesCompared / 1e6).toFixed(1)} MB of DOM each, ${mismatches.length} differences; `
        + `worker decode ${JSON.stringify(entry.decodedInWorker)}; console ${left.messages.length}/${right.messages.length}`);
      for (const mismatch of mismatches.slice(0, 5)) console.log("  ", JSON.stringify(mismatch).slice(0, 600));
    }
  } finally {
    await browser.close();
    for (const server of servers) server.close();
  }
  if (options.out) await writeFile(options.out, JSON.stringify(report, null, 2));
  process.exit(differences === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
