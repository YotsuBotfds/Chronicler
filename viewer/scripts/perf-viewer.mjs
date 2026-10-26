#!/usr/bin/env node
/**
 * Viewer performance measurements (docs/performance/viewer-2026-10.md).
 *
 *   node scripts/perf-viewer.mjs sizes --build main=DIR --build branch=DIR
 *   node scripts/perf-viewer.mjs run --build main=DIR --build branch=DIR \
 *     --bundle guard=FILE --bundle proc32=FILE --runs 5 --out report.json
 *
 * Each `--build` is a production build directory (`npm run build` writes
 * `dist/`). `sizes` reads the JavaScript the build ships: the entry chunk
 * that `index.html` loads, the chunks it preloads, and every chunk, minified
 * and gzip (zlib's default level, as Vite reports it).
 *
 * `run` serves each build from its own local static server and opens it in
 * headless Chromium (Playwright; `require("playwright")`). Per sample, in a
 * fresh browser context:
 *
 * - page load: first contentful paint and the shell's first render;
 * - bundle load: from the file input's `change` event to the first overview
 *   render with the bundle's data (playhead, civilization chips, no loading
 *   card) and to the systems panel's first render, each also to the frame
 *   after it;
 * - main-thread blocking during that load: long tasks (over 50 ms), the
 *   total blocking time (the sum of each task's time over 50 ms), the
 *   longest task and their total;
 * - the JavaScript heap after the load (after a forced garbage collection);
 * - scrubbing: a click on the timeline track, from the click to the commit
 *   plus a forced layout ("commit") and to the frame after it ("frame"),
 *   for consecutive turns and for seeded random jumps, in three scenarios:
 *   the overview with the Event Log, the campaign surface (wars layer and
 *   tab), and the overview with an event pinned in the inspector.
 *
 * Builds alternate within each round (A B, then B A, ...), so drift on a
 * loaded machine falls on both. The report holds every sample and a summary:
 * medians over the runs, with the range (min-max) of the runs.
 */
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFile, readdir, stat, writeFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import path from "node:path";

const require = createRequire(import.meta.url);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".map": "application/json",
};

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const options = { command, builds: [], bundles: [], runs: 5, out: null, consecutive: 100, random: 100,
    pinned: 50, seed: 20261026, headed: false };
  for (let index = 0; index < rest.length; index += 1) {
    const flag = rest[index];
    const value = rest[index + 1];
    const pair = () => {
      const at = value.indexOf("=");
      if (at <= 0) throw new Error(`${flag} expects label=path, got ${value}`);
      return { label: value.slice(0, at), path: path.resolve(value.slice(at + 1)) };
    };
    switch (flag) {
      case "--build": options.builds.push(pair()); index += 1; break;
      case "--bundle": options.bundles.push(pair()); index += 1; break;
      case "--runs": options.runs = Number(value); index += 1; break;
      case "--out": options.out = path.resolve(value); index += 1; break;
      case "--consecutive": options.consecutive = Number(value); index += 1; break;
      case "--random": options.random = Number(value); index += 1; break;
      case "--pinned": options.pinned = Number(value); index += 1; break;
      case "--seed": options.seed = Number(value); index += 1; break;
      case "--headed": options.headed = true; break;
      default: throw new Error(`Unknown option ${flag}`);
    }
  }
  if (!["sizes", "run"].includes(command)) {
    throw new Error("Usage: perf-viewer.mjs sizes|run --build label=dir [--bundle label=file] [--runs N] [--out file]");
  }
  if (options.builds.length === 0) throw new Error("At least one --build label=dir");
  if (command === "run" && options.bundles.length === 0) throw new Error("run needs at least one --bundle label=file");
  return options;
}

// --- Sizes ---------------------------------------------------------------

async function buildSizes(dir) {
  const html = await readFile(path.join(dir, "index.html"), "utf8");
  const entry = /<script[^>]*type="module"[^>]*src="([^"]+)"/.exec(html)?.[1] ?? null;
  const preloads = [...html.matchAll(/<link[^>]*rel="modulepreload"[^>]*href="([^"]+)"/g)].map((match) => match[1]);
  const assets = path.join(dir, "assets");
  const files = (await readdir(assets)).sort();
  const chunks = [];
  for (const name of files) {
    if (!name.endsWith(".js") && !name.endsWith(".css")) continue;
    const bytes = await readFile(path.join(assets, name));
    chunks.push({ name, kind: name.endsWith(".js") ? "js" : "css", bytes: bytes.length, gzip: gzipSync(bytes).length });
  }
  const byName = (href) => chunks.find((chunk) => href && href.endsWith(`/${chunk.name}`)) ?? null;
  const entryChunk = byName(entry);
  const initial = [entryChunk, ...preloads.map(byName)].filter(Boolean);
  const js = chunks.filter((chunk) => chunk.kind === "js");
  const sum = (list, key) => list.reduce((total, chunk) => total + chunk[key], 0);
  return {
    entry: entryChunk,
    initialJs: { files: initial.map((chunk) => chunk.name), bytes: sum(initial, "bytes"), gzip: sum(initial, "gzip") },
    totalJs: { files: js.length, bytes: sum(js, "bytes"), gzip: sum(js, "gzip") },
    css: chunks.filter((chunk) => chunk.kind === "css"),
    chunks,
  };
}

// --- Static server -------------------------------------------------------

function serve(dir) {
  const root = path.resolve(dir);
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      let file = path.join(root, decodeURIComponent(url.pathname));
      if (file !== root && !file.startsWith(root + path.sep)) {
        response.writeHead(403).end();
        return;
      }
      if ((await stat(file)).isDirectory()) file = path.join(file, "index.html");
      const body = await readFile(file);
      response.writeHead(200, {
        "content-type": MIME[path.extname(file)] ?? "application/octet-stream",
        "cache-control": "no-store",
      });
      response.end(body);
    } catch {
      response.writeHead(404).end();
    }
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

// --- In-page instrumentation ---------------------------------------------

/** Runs at document start in every page: long tasks, the file input's change and the first renders. */
function initScript() {
  const perf = { longTasks: [], marks: {} };
  window.__perf = perf;
  const afterFrame = (name) => requestAnimationFrame(() => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => { perf.marks[name] = performance.now(); };
    channel.port2.postMessage(0);
  });
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) perf.longTasks.push({ start: entry.startTime, duration: entry.duration });
    }).observe({ type: "longtask", buffered: true });
  } catch { /* no long-task timing */ }
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.name === "first-contentful-paint") perf.marks.fcp = entry.startTime;
      }
    }).observe({ type: "paint", buffered: true });
  } catch { /* no paint timing */ }
  const conditions = {
    shell: () => !!document.querySelector(".phase75-shell"),
    overview: () => perf.marks.change !== undefined
      && document.querySelector(".phase75-mode-tab.active")?.textContent === "Overview"
      && !!document.querySelector(".phase75-playhead-label")
      && !!document.querySelector(".phase75-civ-chip")
      && !document.querySelector(".phase75-map-loading"),
    systems: () => perf.marks.change !== undefined
      && !!document.querySelector('section[aria-label="Simulation systems"] [role="tabpanel"] > *')
      && !document.querySelector('[data-lazy-fallback]'),
  };
  const check = () => {
    for (const [name, test] of Object.entries(conditions)) {
      if (perf.marks[name] === undefined && test()) {
        perf.marks[name] = performance.now();
        afterFrame(`${name}Frame`);
      }
    }
  };
  new MutationObserver(check).observe(document, { subtree: true, childList: true, characterData: true, attributes: true });
  document.addEventListener("change", (event) => {
    if (event.target instanceof HTMLInputElement && event.target.type === "file" && perf.marks.change === undefined) {
      perf.marks.change = performance.now();
    }
  }, true);
}

/** In the page: click the timeline track at each turn and time the change. */
async function scrubInPage({ turns, total }) {
  const track = document.querySelector(".phase75-turn-track");
  const label = () => document.querySelector(".phase75-playhead-label")?.textContent ?? null;
  const yieldTask = () => new Promise((resolve) => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => resolve();
    channel.port2.postMessage(0);
  });
  const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const samples = [];
  for (const turn of turns) {
    await nextFrame();
    await yieldTask();
    const rect = track.getBoundingClientRect();
    const x = rect.left + ((turn - 1) / Math.max(total - 1, 1)) * rect.width;
    const sample = await new Promise((resolve) => {
      let done = false;
      const t0 = performance.now();
      const observer = new MutationObserver(() => {
        if (done || label() !== `T${turn}`) return;
        done = true;
        observer.disconnect();
        // Mutation records are delivered after React's commit (and its sync effects).
        const script = performance.now() - t0;
        document.body.getBoundingClientRect();
        const commit = performance.now() - t0;
        requestAnimationFrame(() => {
          yieldTask().then(() => resolve({ turn, script, layout: commit - script, commit, frame: performance.now() - t0 }));
        });
      });
      observer.observe(document.body, { subtree: true, childList: true, characterData: true });
      track.dispatchEvent(new MouseEvent("click", {
        bubbles: true, cancelable: true, view: window, clientX: x, clientY: rect.top + rect.height / 2,
      }));
      setTimeout(() => {
        if (!done) {
          done = true;
          observer.disconnect();
          resolve({ turn, script: null, layout: null, commit: null, frame: null, error: `playhead shows ${label()}` });
        }
      }, 10000);
    });
    samples.push(sample);
  }
  return samples;
}

/** In the page: seek without timing (a start position for a scrub). */
async function seekInPage({ turn, total }) {
  const track = document.querySelector(".phase75-turn-track");
  const rect = track.getBoundingClientRect();
  const x = rect.left + ((turn - 1) / Math.max(total - 1, 1)) * rect.width;
  track.dispatchEvent(new MouseEvent("click", {
    bubbles: true, cancelable: true, view: window, clientX: x, clientY: rect.top + rect.height / 2,
  }));
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (document.querySelector(".phase75-playhead-label")?.textContent === `T${turn}`) return true;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  return false;
}

// --- Turn sequences ------------------------------------------------------

function lcg(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

function randomTurns(count, total, seed, avoid) {
  const next = lcg(seed);
  const turns = [];
  let previous = avoid;
  while (turns.length < count) {
    const turn = 1 + Math.floor(next() * total);
    if (turn === previous) continue;
    turns.push(turn);
    previous = turn;
  }
  return turns;
}

// --- One sample ----------------------------------------------------------

async function waitForMark(page, name, timeout = 120000) {
  await page.waitForFunction((mark) => window.__perf.marks[mark] !== undefined, name, { timeout, polling: 50 });
}

async function lazyIdle(page) {
  await page.waitForFunction(() => !document.querySelector("[data-lazy-fallback]"), null, { timeout: 60000, polling: 25 });
}

async function sample(browser, url, bundle, options, total) {
  const context = await browser.newContext({ viewport: { width: 1920, height: 1200 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") errors.push(`${message.type()}: ${message.text()}`);
  });
  await page.addInitScript(initScript);
  const cdp = await context.newCDPSession(page);
  await cdp.send("Performance.enable");

  await page.goto(url, { waitUntil: "load" });
  await waitForMark(page, "shellFrame");
  await page.waitForFunction(() => window.__perf.marks.fcp !== undefined, null, { timeout: 5000, polling: 50 })
    .catch(() => undefined);
  const pageLoad = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    return {
      fcp: window.__perf.marks.fcp ?? null,
      shell: window.__perf.marks.shell,
      shellFrame: window.__perf.marks.shellFrame,
      domContentLoaded: navigation ? navigation.domContentLoadedEventEnd : null,
    };
  });
  // Let page-load tasks (and any idle-time prefetch) finish before the bundle load.
  await page.waitForTimeout(1500);
  const longTasksBefore = await page.evaluate(() => window.__perf.longTasks.length);

  await page.locator('input[type="file"][accept=".json"]').first().setInputFiles(bundle.path);
  await waitForMark(page, "overviewFrame");
  await waitForMark(page, "systemsFrame");
  await lazyIdle(page);
  await page.waitForTimeout(1000);
  const load = await page.evaluate((skip) => {
    const { marks, longTasks } = window.__perf;
    const start = marks.change;
    const end = marks.systemsFrame + 1000;
    const tasks = longTasks.slice(skip).filter((task) => task.start + task.duration >= start && task.start <= end);
    return {
      overview: marks.overview - start,
      overviewFrame: marks.overviewFrame - start,
      systems: marks.systems - start,
      systemsFrame: marks.systemsFrame - start,
      longTaskCount: tasks.length,
      blocking: tasks.reduce((sum, task) => sum + Math.max(0, task.duration - 50), 0),
      longest: tasks.reduce((max, task) => Math.max(max, task.duration), 0),
      longTaskTotal: tasks.reduce((sum, task) => sum + task.duration, 0),
      tasks: tasks.map((task) => ({ start: task.start - start, duration: task.duration })),
    };
  }, longTasksBefore);
  await cdp.send("HeapProfiler.collectGarbage");
  const metrics = (await cdp.send("Performance.getMetrics")).metrics;
  const heap = metrics.find((metric) => metric.name === "JSHeapUsedSize")?.value ?? null;

  const start = Math.max(2, Math.floor(total * 0.4));
  const consecutive = Array.from({ length: Math.min(options.consecutive, total - start) }, (_, index) => start + 1 + index);
  const scrub = {};
  const runScenario = async (name, setup, counts) => {
    await setup();
    await lazyIdle(page);
    if (!(await page.evaluate(seekInPage, { turn: start, total }))) throw new Error(`${name}: seek to ${start} failed`);
    await lazyIdle(page);
    const consecutiveTurns = consecutive.slice(0, counts.consecutive);
    const result = { consecutive: await page.evaluate(scrubInPage, { turns: consecutiveTurns, total }) };
    const last = consecutiveTurns[consecutiveTurns.length - 1] ?? start;
    result.random = await page.evaluate(scrubInPage, {
      turns: randomTurns(counts.random, total, options.seed, last), total,
    });
    scrub[name] = result;
  };

  await runScenario("overview-events", async () => {
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await page.getByRole("button", { name: "Event Log", exact: true }).click();
  }, { consecutive: options.consecutive, random: options.random });

  await runScenario("campaign", async () => {
    await page.getByRole("button", { name: "Campaign", exact: true }).click();
  }, { consecutive: options.consecutive, random: options.random });

  await runScenario("overview-pinned-event", async () => {
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await page.getByRole("button", { name: "Event Log", exact: true }).click();
    if (!(await page.evaluate(seekInPage, { turn: start, total }))) throw new Error("pin: seek failed");
    const row = page.locator(".phase75-event-row").first();
    await row.click();
  }, { consecutive: options.pinned, random: options.pinned });

  await context.close();
  return { pageLoad, load, heap, scrub, errors };
}

// --- Summary -------------------------------------------------------------

function quantile(values, q) {
  const sorted = values.filter((value) => typeof value === "number" && Number.isFinite(value)).sort((a, b) => a - b);
  if (sorted.length === 0) return null;
  const position = (sorted.length - 1) * q;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}

function spread(values) {
  const clean = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  return { median: quantile(clean, 0.5), min: clean.length ? Math.min(...clean) : null,
    max: clean.length ? Math.max(...clean) : null, n: clean.length };
}

function summarize(samples) {
  const groups = new Map();
  for (const entry of samples) {
    const key = `${entry.bundle}\u0000${entry.build}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(entry.result);
  }
  const summary = [];
  for (const [key, results] of groups) {
    const [bundle, build] = key.split("\u0000");
    const metric = (pick) => spread(results.map(pick));
    const row = {
      bundle, build, runs: results.length,
      fcp: metric((r) => r.pageLoad.fcp),
      shellFrame: metric((r) => r.pageLoad.shellFrame),
      loadOverview: metric((r) => r.load.overviewFrame),
      loadSystems: metric((r) => r.load.systemsFrame),
      blocking: metric((r) => r.load.blocking),
      longest: metric((r) => r.load.longest),
      longTaskTotal: metric((r) => r.load.longTaskTotal),
      heapMiB: metric((r) => (r.heap === null ? null : r.heap / 2 ** 20)),
      scrub: {},
    };
    for (const scenario of Object.keys(results[0].scrub)) {
      row.scrub[scenario] = {};
      for (const pattern of ["consecutive", "random"]) {
        const per = (field, q) => metric((r) => quantile(r.scrub[scenario][pattern].map((s) => s[field]), q));
        row.scrub[scenario][pattern] = {
          scriptMedian: per("script", 0.5), scriptP95: per("script", 0.95),
          layoutMedian: per("layout", 0.5),
          commitMedian: per("commit", 0.5), commitP95: per("commit", 0.95),
          frameMedian: per("frame", 0.5), frameP95: per("frame", 0.95),
          failures: results.reduce((n, r) => n + r.scrub[scenario][pattern].filter((s) => s.commit === null).length, 0),
        };
      }
    }
    summary.push(row);
  }
  return summary;
}

const fmt = (stat, digits = 1) => (stat.median === null ? "n/a"
  : `${stat.median.toFixed(digits)} (${stat.min.toFixed(digits)}-${stat.max.toFixed(digits)})`);

function printSummary(summary) {
  for (const row of summary) {
    console.log(`\n${row.bundle} / ${row.build} (${row.runs} runs; median (min-max) of the runs, ms)`);
    console.log(`  FCP ${fmt(row.fcp)}  shell frame ${fmt(row.shellFrame)}`);
    console.log(`  load: overview frame ${fmt(row.loadOverview)}  systems frame ${fmt(row.loadSystems)}`);
    console.log(`  blocking ${fmt(row.blocking)}  longest task ${fmt(row.longest)}  long tasks total ${fmt(row.longTaskTotal)}`);
    console.log(`  heap after load ${fmt(row.heapMiB)} MiB`);
    for (const [scenario, patterns] of Object.entries(row.scrub)) {
      for (const [pattern, stats] of Object.entries(patterns)) {
        console.log(`  scrub ${scenario} ${pattern}: script median ${fmt(stats.scriptMedian, 2)} p95 ${fmt(stats.scriptP95, 2)}`
          + `  layout ${fmt(stats.layoutMedian, 2)}  frame median ${fmt(stats.frameMedian, 2)} p95 ${fmt(stats.frameP95, 2)}`
          + `${stats.failures ? `  FAILURES ${stats.failures}` : ""}`);
      }
    }
  }
}

// --- Main ----------------------------------------------------------------

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const sizes = {};
  for (const build of options.builds) {
    sizes[build.label] = await buildSizes(build.path);
  }
  for (const [label, size] of Object.entries(sizes)) {
    console.log(`${label}: entry ${size.entry?.name} ${size.entry?.bytes} B (gzip ${size.entry?.gzip}); `
      + `initial JS ${size.initialJs.bytes} B (gzip ${size.initialJs.gzip}); `
      + `all JS ${size.totalJs.files} files ${size.totalJs.bytes} B (gzip ${size.totalJs.gzip})`);
  }
  if (options.command === "sizes") {
    if (options.out) await writeFile(options.out, JSON.stringify({ sizes }, null, 2));
    return;
  }

  const { chromium } = require("playwright");
  const servers = [];
  const urls = {};
  for (const build of options.builds) {
    const server = await serve(build.path);
    servers.push(server);
    urls[build.label] = `http://127.0.0.1:${server.address().port}/`;
  }
  const totals = {};
  for (const bundle of options.bundles) {
    const parsed = JSON.parse(await readFile(bundle.path, "utf8"));
    totals[bundle.label] = parsed.metadata?.total_turns ?? (parsed.history_delta ?? parsed.history).length;
  }
  const browser = await chromium.launch({ headless: !options.headed });
  const samples = [];
  try {
    for (let run = 0; run < options.runs; run += 1) {
      const order = run % 2 === 0 ? options.builds : [...options.builds].reverse();
      for (const bundle of options.bundles) {
        for (const build of order) {
          const started = Date.now();
          const result = await sample(browser, urls[build.label], bundle, options, totals[bundle.label]);
          samples.push({ run, bundle: bundle.label, build: build.label, result });
          console.log(`run ${run + 1}/${options.runs} ${bundle.label} ${build.label}: load ${result.load.overviewFrame.toFixed(0)} ms, `
            + `blocking ${result.load.blocking.toFixed(0)} ms (${((Date.now() - started) / 1000).toFixed(1)} s)`
            + (result.errors.length ? `; ${result.errors.length} console messages` : ""));
        }
      }
    }
  } finally {
    await browser.close();
    for (const server of servers) server.close();
  }
  const summary = summarize(samples);
  printSummary(summary);
  const report = {
    generated: new Date().toISOString(),
    chromium: browser.version(),
    node: process.version,
    options: { runs: options.runs, consecutive: options.consecutive, random: options.random, pinned: options.pinned,
      seed: options.seed, builds: options.builds.map((build) => build.label),
      bundles: options.bundles.map((bundle) => ({ label: bundle.label, turns: totals[bundle.label] })) },
    sizes,
    summary,
    samples,
  };
  if (options.out) {
    await writeFile(options.out, JSON.stringify(report, null, 2));
    console.log(`\nReport written to ${options.out}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
