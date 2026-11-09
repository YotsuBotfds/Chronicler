#!/usr/bin/env node
/**
 * Browser QA of the recovery chain view (PL5c) on the Livelihoods tab, on a
 * production build in headless Chromium (Playwright; `require("playwright")`).
 * Opt-in, not CI. Modelled on qa-productive-recovery.mjs and
 * qa-household-retail.mjs.
 *
 *   PYTHONPATH=../src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
 *   node scripts/qa-recovery-chain.mjs [--build dist] --out DIR \
 *     [--python ~/.venvs/native-hrn2/bin/python] [--seed 23] [--turns 60] \
 *     [--worldgen template|procedural] [--parts chain,variant,subset]
 *
 * It runs the real simulation itself, one process at a time, on a
 * development world only (template seeds 1, 3, 7, 9, 11, 23, 42; procedural
 * 32x10 seeds 7, 11, 13, 17, 21, 31; anything else is refused), with the
 * chain switches `--agents hybrid --food-allocation --workshops
 * --operating-wear --repair-projects --timber-stock --household-retail
 * --household-retail-boundary paid_work --timber-supply --recovery-crews
 * --remittances` and the prerequisites the productive-recovery runs use
 * (`--grain-reserves --public-grain-shipments --scholarship --techniques
 * --academy-services --grain-storage`, `--simulate-only`). `--python` must
 * import `chronicler` (set PYTHONPATH) and a native extension built from this
 * source's Rust; its `scripts/check_python_env.py --expect native` output
 * is kept in the report. Parts:
 *
 * - chain: the chain bundle is opened with "Open saved world file" at
 *   1440x900 and 390x844 (touch). The expected chain of every region and
 *   snapshot is read from the bundle with `--python`
 *   (`chronicler.bundle_codec`), independently of the viewer's readers. The
 *   view's default region must be a region with a real chain (an RS2 stall
 *   for want of timber and a delivery from one of its expeditions). The
 *   slider is moved with keys to the chain's stall, delivery, first store
 *   hold, first paid granary crew, a purchase and the last snapshot; at each
 *   stop the heading names the slider's turn and the "at snapshot" table's
 *   links show the real values of that snapshot (stall reasons, expedition
 *   ids, store held, granary condition, PL3 wages and crew ids, pilot persons
 *   and purchases, remittances), each with its join (stable id or region
 *   only). The region picker (labelled "Region") is moved to another region
 *   and back, and the tables follow it. The text alternative: the strip is a
 *   labelled group whose rows name their runs, and the snapshots the repair
 *   row calls stalled are exactly the turn table's stalled rows; "Show every
 *   snapshot" lists every snapshot; a row's seek button moves the slider. No
 *   NaN or undefined; at 390 px no horizontal page overflow.
 * - variant: a constructed variant of the chain bundle (written to `--out`,
 *   labelled constructed): remittances removed from one snapshot, the retail
 *   frame and PL3 receipts blanked at another, timber supply misdated at a
 *   third. The view must say unknown (not zero) and rejected as malformed
 *   there, and read the neighbouring snapshots normally.
 * - subset: a second run of the same world with only `--food-allocation
 *   --workshops --repair-projects --recovery-crews --household-retail
 *   --household-retail-boundary paid_work` (timber supply, timber stock and
 *   remittances off): the view mounts, says off for the expedition, forest,
 *   store and remittance links and leaves them out of the turn table.
 *
 * Console errors and page errors fail a part. `--out` is emptied first;
 * `report.json`, screenshots (JPEG, device scale 1), the runs and the variant
 * go there. Exits 1 when a check fails.
 */
import { loadPlaywright } from "./lib/playwright.mjs";
import { createServer } from "node:http";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const VIEWER = path.resolve(HERE, "..");
/** Written into `--out` when the script creates it: only a directory holding it may be emptied on a later run. */
const MARKER = ".qa-recovery-chain-output";

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".json": "application/json", ".wasm": "application/wasm",
};
const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
  phone: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 },
};
/** Development worlds only. */
const DEVELOPMENT = { template: [1, 3, 7, 9, 11, 23, 42], procedural: [7, 11, 13, 17, 21, 31] };
const BASE = ["--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments", "--scholarship",
  "--techniques", "--academy-services", "--grain-storage"];
const CHAIN = ["--food-allocation", "--workshops", "--operating-wear", "--repair-projects", "--timber-stock",
  "--household-retail", "--household-retail-boundary", "paid_work", "--timber-supply", "--recovery-crews", "--remittances"];
const SUBSET = ["--food-allocation", "--workshops", "--repair-projects", "--recovery-crews", "--household-retail",
  "--household-retail-boundary", "paid_work"];
const HEADING = "Recovery chain";
const BAD_TEXT = /\bNaN\b|\bundefined\b/;
const LINK = {
  repair: "Repair need (RS2)", expedition: "Woodcutting expedition (PL1)", forest: "Forest stock (L3)",
  store: "Timber store to repair", granary: "Granary condition", wages: "Wages paid (PL3, RS2, PL1)",
  retail: "Food purchases (PL4)", remittances: "Remittances in (RS4)",
};
const JOIN = { repair: "Stable id", expedition: "Region only", forest: "Stable id", store: "Region only", granary: "Stable id",
  wages: "Stable id", retail: "Region only", remittances: "Region only" };

function parseArgs(argv) {
  const options = { build: path.join(HERE, "..", "dist"), out: null, python: "python3", seed: 23, turns: 60,
    worldgen: "template", parts: "chain,variant,subset" };
  for (let index = 0; index < argv.length; index += 2) {
    const [flag, value] = [argv[index], argv[index + 1]];
    if (value === undefined) throw new Error(`${flag} needs a value`);
    if (flag === "--build") options.build = path.resolve(value);
    else if (flag === "--out") options.out = path.resolve(value);
    else if (flag === "--python") options.python = value;
    else if (flag === "--seed") options.seed = Number(value);
    else if (flag === "--turns") options.turns = Number(value);
    else if (flag === "--worldgen") options.worldgen = value;
    else if (flag === "--parts") options.parts = value;
    else throw new Error(`Unknown option ${flag}`);
  }
  options.parts = new Set(options.parts.split(",").filter(Boolean));
  if (!options.out) throw new Error("Usage: qa-recovery-chain.mjs --out DIR [--python PY] [--seed N] [--turns N] [--worldgen template|procedural] [--build DIR] [--parts chain,variant,subset]");
  if (!DEVELOPMENT[options.worldgen]?.includes(options.seed))
    throw new Error(`Refusing ${options.worldgen} seed ${options.seed}: only development worlds may be run (${JSON.stringify(DEVELOPMENT)})`);
  if (!Number.isInteger(options.turns) || options.turns < 20 || options.turns > 200) throw new Error("--turns must be 20-200");
  return options;
}

const options = parseArgs(process.argv.slice(2));
const report = { generated: new Date().toISOString(), build: options.build, world: { worldgen: options.worldgen, seed: options.seed,
  turns: options.turns }, runs: {}, parts: {} };
let failures = 0;

function serve(dir) {
  const root = path.resolve(dir);
  const server = createServer((request, response) => {
    try {
      let file = path.join(root, decodeURIComponent(new URL(request.url ?? "/", "http://x").pathname));
      if (file !== root && !file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
      if (statSync(file).isDirectory()) file = path.join(file, "index.html");
      response.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" });
      response.end(readFileSync(file));
    } catch {
      response.writeHead(404).end();
    }
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

function partLog(name) {
  const part = { checks: [], messages: [], screenshots: [], notes: [] };
  report.parts[name] = part;
  part.check = (label, ok, detail = "") => {
    part.checks.push({ name: label, ok: !!ok, detail: String(detail).slice(0, 600) });
    if (!ok) failures += 1;
    console.log(`${ok ? "ok  " : "FAIL"} [${name}] ${label}${detail && !ok ? `: ${String(detail).slice(0, 300)}` : ""}`);
  };
  part.watch = (page, tag) => {
    page.on("pageerror", (error) => part.messages.push(`${tag} pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") part.messages.push(`${tag} ${message.type()}: ${message.text()}`);
    });
  };
  part.shot = async (locator, file) => {
    const target = path.join(options.out, file);
    await locator.screenshot({ path: target, type: "jpeg", quality: 60, scale: "css", animations: "disabled" });
    part.screenshots.push(target);
  };
  part.errorsFree = (label) => {
    const errors = part.messages.filter((m) => / (pageerror|error):/.test(m));
    part.check(`${label}: no console or page errors`, errors.length === 0, errors.join(" | "));
  };
  return part;
}

// ---------------------------------------------------------------- the runs and their expected chains

function simulate(label, flags) {
  const dir = path.join(options.out, "runs", label);
  mkdirSync(dir, { recursive: true });
  const world = options.worldgen === "procedural" ? ["--worldgen", "procedural", "--regions", "32", "--civs", "10"] : [];
  const args = ["-m", "chronicler.main", "--seed", String(options.seed), "--turns", String(options.turns), ...world, ...BASE, ...flags,
    "--output", path.join(dir, "chronicle.md"), "--state", path.join(dir, "state.json")];
  const started = Date.now();
  const run = spawnSync(options.python, args, { cwd: dir, encoding: "utf8", maxBuffer: 1 << 26,
    env: { ...process.env, PYTHONHASHSEED: "0", RAYON_NUM_THREADS: "1" } });
  writeFileSync(path.join(dir, "run.log"), `${run.stdout}\n${run.stderr}`);
  report.runs[label] = { command: `${options.python} ${args.join(" ")}`, exit: run.status, seconds: (Date.now() - started) / 1000 };
  if (run.status !== 0) throw new Error(`${label} run failed (${run.status}): ${run.stderr.slice(-800)}`);
  return path.join(dir, "chronicle_bundle.json");
}

const EXPECT_PY = String.raw`
import json, sys
from chronicler.bundle_codec import load_bundle
b = load_bundle(sys.argv[1])
R = len(b["world_state"]["regions"])
def liv(s, k):
    l = s.get("livelihoods")
    return l.get(k) if isinstance(l, dict) else None
on = {k: any(liv(s, k) is not None for s in b["history"]) for k in
      ("repair_projects", "timber_supply", "timber_stock", "recovery_crews", "household_retail", "remittances")}
turns = {}
for s in b["history"]:
    T = s["turn"]
    rp, ts, rc = liv(s, "repair_projects"), liv(s, "timber_supply"), liv(s, "recovery_crews")
    hr, rm = liv(s, "household_retail"), liv(s, "remittances")
    storage = (s.get("grain_reserves") or {}).get("storage")
    rows = []
    for r in range(R):
        e = {}
        if rp is not None:
            e["open"] = [p["pid"] for p in rp["projects"] if p["region"] == r]
            e["closed_now"] = [[p["pid"], p["status"]] for p in rp["closed"] if p["region"] == r and p["closed_turn"] == rp["source_turn"]]
            e["stalls"] = None if rp["receipts"] is None else [[x["pid"], x["reasons"]] for x in rp["receipts"]
                                                                if x["region"] == r and x["status"] == "stalled"]
            e["rs2_wages"] = None if rp["receipts"] is None else sum(x["wages_milli"] for x in rp["receipts"]
                                                                     if x["region"] == r and x["kind"] == "workshop")
            e["holders"] = None if rp["receipts"] is None else [[x["pid"], x["timber_held"]] for x in rp["receipts"]
                                                                if x["region"] == r and x["timber_held"] > 0]
        if ts is not None:
            e["live"] = [x["eid"] for x in ts["expeditions"] if x["home"] == r]
            e["delivered"] = sum(x["delivered"] for x in ts["closed"] if x["home"] == r and x["ended_turn"] == ts["source_turn"]
                                 and x["status"] == "delivered")
            st = None if ts["stores"] is None else [x for x in ts["stores"] if x["region"] == r]
            e["store"] = None if st is None else (st[0] if st else "none")
            e["pl1_wages"] = None if ts["receipts"] is None else sum(x["wages_milli"] for x in ts["receipts"] if x["home"] == r)
        if rc is not None:
            g = None if rc["receipts"] is None else [x for x in rc["receipts"] if x["region"] == r and x["kind"] == "granary"]
            e["pl3_wages"] = None if g is None else sum(m["wage_milli"] for x in g for m in x["members"])
            e["pl3_crew"] = None if g is None else [m["agent_id"] for x in g for m in x["members"]]
            k = None if rc["receipts"] is None else [x for x in rc["receipts"] if x["region"] == r]
            e["pl3_farm"] = None if k is None else {kind: sum(x["farm_time_removed"] for x in k if x["kind"] == kind)
                                                    for kind in ("granary", "workshop")}
        if storage is not None:
            a = storage["assets"][r]
            e["condition"] = None if a is None else a["condition"]
        if hr is not None:
            f = None if hr["regions"] is None else [x for x in hr["regions"] if x["region"] == r]
            if f is None:
                e["retail"] = None
            elif not f:
                e["retail"] = "not_pilot"
            else:
                p = f[0]["provisioning"]
                e["retail"] = {"opened": f[0]["opened_turn"], "provisioned": p is not None,
                               **({k: int(p[k]) for k in ("persons", "children", "paid_milli", "priced_out_persons")} if p else {})}
        if rm is not None:
            e["inflow"] = None if rm["regions"] is None else sum(x["inflow_milli"] for x in rm["regions"] if x["region"] == r)
        rows.append(e)
    turns[T] = rows
json.dump({"regions": [x["name"] for x in b["world_state"]["regions"]], "total": b["metadata"]["total_turns"], "on": on,
           "turns": turns}, sys.stdout)
`;

function expectations(file) {
  const run = spawnSync(options.python, ["-c", EXPECT_PY, file], { env: process.env, encoding: "utf8", maxBuffer: 1 << 28 });
  if (run.status !== 0) throw new Error(`reading ${file} failed: ${run.stderr}`);
  const out = JSON.parse(run.stdout);
  out.at = (turn, region) => out.turns[String(turn)][region];
  out.list = Object.keys(out.turns).map(Number).sort((a, b) => a - b);
  return out;
}

/** The viewer's number format (toLocaleString, en-US in headless Chromium). */
const fmt = (value, digits = 2) => (Math.abs(value) < 5e-7 ? 0 : value).toLocaleString("en-US", { maximumFractionDigits: digits });
const coins = (milli) => fmt(milli / 1000, 3);

/** Each region's chain steps recorded at some snapshot (a no_timber stall, timber delivered, the store holding timber,
 * wages paid, food bought) and its timber delivered: the view shows first a region with the most steps, then the most timber. */
function fullest(x) {
  const score = x.regions.map((_, r) => {
    const rows = x.list.map((t) => x.at(t, r));
    const steps = [rows.some((e) => (e.stalls ?? []).some(([, reasons]) => reasons.includes("no_timber"))),
      rows.some((e) => e.delivered > 0), rows.some((e) => e.store && e.store !== "none" && e.store.held > 0),
      rows.some((e) => (e.pl3_wages ?? 0) + (e.rs2_wages ?? 0) + (e.pl1_wages ?? 0) > 0),
      rows.some((e) => e.retail && e.retail !== "not_pilot" && e.retail.paid_milli > 0)].filter(Boolean).length;
    return [steps, rows.reduce((a, e) => a + (e.delivered ?? 0), 0)];
  });
  const top = score.reduce((m, s) => (s[0] > m[0] || (s[0] === m[0] && s[1] > m[1]) ? s : m), [-1, -1]);
  return score.map((s, r) => (s[0] === top[0] && Math.abs(s[1] - top[1]) < 1e-9 ? r : -1)).filter((r) => r >= 0);
}

/** Regions with a real chain: a stall for want of timber, and later a delivery from one of their expeditions. */
function chainRegions(x) {
  return x.regions.map((_, r) => r).filter((r) => {
    const stall = x.list.find((t) => (x.at(t, r).stalls ?? []).some(([, reasons]) => reasons.includes("no_timber")));
    return stall !== undefined && x.list.some((t) => t > stall && x.at(t, r).delivered > 0);
  });
}

// ---------------------------------------------------------------- the page

/** In the page: the recovery chain section. */
function readChain() {
  const panel = document.querySelector('.systems-shell [role="tabpanel"]');
  const section = panel ? [...panel.querySelectorAll("section")].find((s) => (s.querySelector("h3")?.textContent ?? "").startsWith("Recovery chain")) : null;
  const tables = section ? [...section.querySelectorAll("table")] : [];
  const now = tables.find((t) => / at snapshot \d+$/.test(t.getAttribute("aria-label") ?? "")) ?? null;
  const over = tables.find((t) => / over snapshots$/.test(t.getAttribute("aria-label") ?? "")) ?? null;
  const links = {};
  for (const tr of now ? [...now.querySelectorAll("tbody tr")] : []) {
    const cells = [...tr.querySelectorAll("td")].map((td) => td.textContent ?? "");
    links[tr.querySelector("th")?.textContent ?? ""] = { what: cells[0], joined: cells[1], tradeoff: cells[2] };
  }
  const strip = section?.querySelector('[role="group"]') ?? null;
  return {
    mounted: !!section,
    heading: section?.querySelector("h3")?.textContent ?? null,
    notes: section ? [...section.querySelectorAll(".systems-note")].map((n) => n.textContent ?? "") : [],
    region: section?.querySelector("select")?.value ?? null,
    regionLabel: section?.querySelector("select") ? (document.querySelector(`label[for="${section.querySelector("select").id}"]`)?.textContent ?? null) : null,
    nowLabel: now?.getAttribute("aria-label") ?? null,
    overLabel: over?.getAttribute("aria-label") ?? null,
    links,
    columns: over ? [...over.querySelectorAll("thead th")].map((th) => th.textContent ?? "") : [],
    rows: over ? [...over.querySelectorAll("tbody tr")].map((tr) => ({ turn: Number(tr.querySelector("th")?.textContent),
      current: tr.getAttribute("aria-current") === "true", cells: [...tr.querySelectorAll("td")].map((td) => td.textContent ?? "") })) : [],
    stripLabel: strip?.getAttribute("aria-label") ?? null,
    stripRows: strip ? [...strip.querySelectorAll('[role="img"]')].map((e) => e.getAttribute("aria-label") ?? "") : [],
    checkbox: section ? !!section.querySelector('input[type="checkbox"]') : false,
    text: section?.innerText ?? "",
    playhead: document.querySelector(".phase75-playhead-label")?.textContent ?? null,
    slider: document.querySelector('[role="slider"]')?.getAttribute("aria-valuenow") ?? null,
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  };
}

async function settled(page) {
  let previous = null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const current = await page.evaluate(readChain);
    if (previous && current.text === previous.text && current.playhead === previous.playhead) return current;
    previous = current;
  }
  return previous;
}

const waitPlayhead = (page, turn) => page.waitForFunction((value) =>
  document.querySelector(".phase75-playhead-label")?.textContent === value, `T${turn}`, { timeout: 20000 });

async function loadBundle(page, file, regions) {
  await page.getByLabel("Open saved world file").setInputFiles(file);
  await page.waitForFunction((count) => document.querySelector(".phase75-mode-tab.active")?.textContent === "Overview"
    && document.querySelectorAll(".phase75-region-node").length === count && !!document.querySelector(".phase75-playhead-label")
    && !document.querySelector("[data-lazy-fallback]") && !document.querySelector(".saved-world-loading"),
  regions, { timeout: 120000, polling: 50 });
  await page.waitForSelector(".systems-shell [role=tab]", { timeout: 60000 });
  await page.getByRole("tab", { name: "Livelihoods", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.systems-shell [role="tabpanel"]')?.getAttribute("aria-label") === "Livelihoods",
    null, { timeout: 20000 });
}

/** Seek with keys only: Home, PageUp by tens, ArrowRight by ones. */
async function seek(page, turn) {
  const slider = page.getByRole("slider", { name: "Historical turn" });
  await slider.focus();
  await slider.press("Home");
  for (let i = 0; i < Math.floor((turn - 1) / 10); i += 1) await slider.press("PageUp");
  for (let i = 0; i < (turn - 1) % 10; i += 1) await slider.press("ArrowRight");
  await waitPlayhead(page, turn);
  return settled(page);
}

async function pickRegion(page, region) {
  await chainSection(page).getByLabel("Region", { exact: true }).selectOption(String(region));
  return settled(page);
}

async function newPage(browser, viewportName, part, url) {
  const context = await browser.newContext(VIEWPORTS[viewportName]);
  const page = await context.newPage();
  part.watch(page, viewportName);
  await page.goto(url, { waitUntil: "load" });
  await page.waitForSelector(".phase75-shell");
  return { context, page };
}

const chainSection = (page) => page.locator('.systems-shell [role="tabpanel"] section[aria-label="Recovery chain"]');

/** The "at snapshot" table shows the expected values of this region and snapshot. */
function checkValues(part, tag, state, turn, name, e, on) {
  part.check(`${tag}: heading and slider at snapshot ${turn}`, state.heading === `${HEADING} · snapshot ${turn}` && state.slider === String(turn),
    `${state.heading} ${state.slider}`);
  part.check(`${tag}: the at-snapshot table names ${name} and snapshot ${turn}`, state.nowLabel === `Recovery chain in ${name} at snapshot ${turn}`, state.nowLabel);
  for (const [key, title] of Object.entries(LINK)) {
    const shown = state.links[title];
    part.check(`${tag}: ${title} says how it is joined (${JOIN[key]})`, shown?.joined.startsWith(`${JOIN[key]}: `), shown?.joined);
  }
  const L = (key) => state.links[LINK[key]]?.what ?? "";
  const need = (label, ok, detail) => part.check(`${tag}: ${label}`, ok, detail);
  if (on.repair_projects) {
    for (const pid of e.open) need(`repair: open project #${pid} shown`, L("repair").includes(`project #${pid} `), L("repair"));
    for (const [pid, reasons] of e.stalls ?? []) need(`repair: project #${pid} stalled (${reasons.join(", ")})`,
      new RegExp(`project #${pid} .*stalled: `).test(L("repair")) && (!reasons.includes("no_timber") || L("repair").includes("no free timber")), L("repair"));
    for (const [pid, status] of e.closed_now) need(`repair: project #${pid} ${status} this turn`, L("repair").includes(`project #${pid} `)
      && L("repair").includes(`${status} this turn`), L("repair"));
    if (!e.open.length && !e.closed_now.length) need("repair: no project open", L("repair").startsWith("No repair project open in the region."), L("repair"));
  } else need("repair: off", L("repair").startsWith("Off: "), L("repair"));
  if (on.timber_supply) {
    for (const eid of e.live) need(`expedition: #${eid} shown`, L("expedition").includes(`Expedition #${eid} `), L("expedition"));
    if (e.delivered > 0) need(`expedition: delivered ${fmt(e.delivered)}`, L("expedition").includes(`delivered ${fmt(e.delivered)} of`), L("expedition"));
    if (e.store === "none") need("store: none", L("store") === "No timber store in the region.", L("store"));
    else if (e.store) need(`store: ${fmt(e.store.held)} held, ${fmt(e.store.closing)} left`,
      L("store").includes(`${fmt(e.store.delivered)} delivered, ${fmt(e.store.held)} held for repairs`) && L("store").includes(`${fmt(e.store.closing)} left`), L("store"));
  } else {
    for (const key of ["expedition", "forest", "store"]) need(`${key}: off`, L(key).startsWith("Off: Timber supply (PL1) is off"), L(key));
  }
  if (on.timber_supply && on.repair_projects && e.store && e.store !== "none" && e.holders) {
    const sole = e.store.held > 0 && e.holders.length === 1;
    need(`store: ${sole ? "the sole holder's hold is attributed to the store" : "no hold is attributed to the store by elimination"}`,
      sole ? L("store").includes(`Only project #${e.holders[0][0]} held timber`) : !/can only/.test(L("store")), L("store"));
    if (e.store.held <= 0 && e.holders.length) need("store: a hold the store did not give is said to come from other free timber",
      L("store").includes("The store gave the repairs nothing this turn"), L("store"));
  }
  if (on.recovery_crews && e.pl3_farm) {
    const trade = state.links[LINK.wages]?.tradeoff ?? "";
    for (const [kind, v] of Object.entries(e.pl3_farm)) if (v > 0) need(`wages tradeoff: PL3 ${kind} crews took ${fmt(v)} farmer-turns`,
      trade.includes(`farm labour taken by PL3 ${kind} crews: ${fmt(v)} farmer-turns`), trade);
  }
  if (e.condition !== undefined) need(e.condition === null ? "granary: no granary" : `granary: condition ${fmt(e.condition, 3)}`,
    e.condition === null ? L("granary").startsWith("No granary") : L("granary").startsWith(`Condition ${fmt(e.condition, 3)} `), L("granary"));
  if (on.recovery_crews && e.pl3_wages !== null) {
    if (e.pl3_wages > 0) need(`wages: PL3 crew ${e.pl3_crew.join(", ")} paid ${coins(e.pl3_wages)}`,
      L("wages").includes(`(${e.pl3_crew.join(", ")}): paid ${coins(e.pl3_wages)} coins`), L("wages"));
    const total = e.pl3_wages + (e.rs2_wages ?? 0) + (e.pl1_wages ?? 0);
    if (e.rs2_wages !== null && e.pl1_wages !== null && e.pl1_wages !== undefined)
      need(`wages: total ${coins(total)} coins`, L("wages").endsWith(`Total paid in the region: ${coins(total)} coins.`), L("wages"));
  }
  if (on.household_retail) {
    const r = e.retail;
    if (r === "not_pilot") need("retail: not a pilot region", L("retail").startsWith("Not a pilot region this turn"), L("retail"));
    else if (r && r.provisioned) need(`retail: ${r.persons} people, paid ${coins(r.paid_milli)} coins`,
      L("retail").includes(`: ${r.persons} people (${r.children} children)`) && L("retail").includes(`paid ${coins(r.paid_milli)} coins`), L("retail"));
    if (r && r.provisioned) need(`retail tradeoff: ${r.priced_out_persons} priced out`, r.priced_out_persons > 0
      ? state.links[LINK.retail].tradeoff.startsWith(`priced out: ${r.priced_out_persons} people`) : state.links[LINK.retail].tradeoff === "nobody priced out",
    state.links[LINK.retail]?.tradeoff);
  }
  if (on.remittances && e.inflow !== null) need(`remittances: ${coins(e.inflow)} in`, e.inflow > 0
    ? L("remittances").startsWith(`${coins(e.inflow)} coins came in`) : L("remittances").startsWith("Nothing came in"), L("remittances"));
  else if (!on.remittances) need("remittances: off", L("remittances").startsWith("Off: Remittances (RS4) is off"), L("remittances"));
  part.check(`${tag}: no NaN or undefined`, !BAD_TEXT.test(state.text), state.text.match(/.{0,60}(NaN|undefined).{0,60}/)?.[0]);
}

function checkFits(part, tag, state, viewportName) {
  if (viewportName === "phone") part.check(`${tag}: no horizontal page overflow`, state.scrollWidth <= state.innerWidth + 1, `${state.scrollWidth} > ${state.innerWidth}`);
}

// ---------------------------------------------------------------- parts

async function partChain(browser, url, bundle, x) {
  const part = partLog("chain");
  const chains = chainRegions(x);
  part.check("the run has a chain region (a no_timber stall, then a delivery from its expedition)", chains.length > 0, JSON.stringify(chains));
  part.notes.push(`chain regions: ${chains.map((r) => x.regions[r]).join(", ")}`);
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part, url);
    await loadBundle(page, bundle, x.regions.length);
    const tag = viewportName;
    const slider = page.getByRole("slider", { name: "Historical turn" });
    await slider.focus();
    await slider.press("End");
    await waitPlayhead(page, x.total);
    let state = await settled(page);
    part.check(`${tag}: the chain view is mounted on the Livelihoods tab`, state.mounted, state.heading);
    part.check(`${tag}: the region picker is labelled "Region"`, state.regionLabel === "Region", state.regionLabel);
    const region = Number(state.region);
    part.check(`${tag}: the default region has a real chain`, chains.includes(region), `${state.region} not in ${chains}`);
    part.check(`${tag}: the default region's chain goes furthest (most steps, then most timber delivered)`, fullest(x).includes(region),
      `${state.region} not in ${fullest(x)}`);
    const name = x.regions[region];
    const R = (t) => x.at(t, region);
    const stall = x.list.find((t) => (R(t).stalls ?? []).some(([, reasons]) => reasons.includes("no_timber")));
    const delivery = x.list.find((t) => t > stall && R(t).delivered > 0);
    const hold = x.list.find((t) => t >= delivery && R(t).store && R(t).store !== "none" && R(t).store.held > 0);
    const paid = x.list.find((t) => (R(t).pl3_wages ?? 0) > 0);
    const bought = x.list.find((t) => t > (paid ?? 0) && R(t).retail?.provisioned && R(t).retail.paid_milli > 0);
    const stops = [...new Set([stall, delivery, hold, paid, bought, x.total].filter((t) => t !== undefined))];
    part.notes.push(`${tag}: ${name}: stall ${stall}, delivery ${delivery}, store hold ${hold}, PL3 wage ${paid}, purchase ${bought}`);
    part.check(`${tag}: the chain's stops are found (stall, delivery, store hold, paid crew, purchase)`,
      [stall, delivery, hold, paid, bought].every((t) => t !== undefined), JSON.stringify({ stall, delivery, hold, paid, bought }));
    for (const turn of stops) {
      state = await seek(page, turn);
      checkValues(part, `${tag} ${name} T${turn}`, state, turn, name, R(turn), x.on);
      checkFits(part, `${tag} T${turn}`, state, viewportName);
      if (turn === hold || (viewportName === "phone" && turn === stall))
        await part.shot(chainSection(page), `${viewportName}-chain-${name.replace(/\W+/g, "-")}-T${turn}.jpg`);
    }
    // The text alternative: strip rows are named, and the stalled runs are the table's stalled rows.
    state = await seek(page, hold ?? x.total);
    part.check(`${tag}: the strip is a labelled group`, state.stripLabel === `Recovery chain in ${name} over snapshots`, state.stripLabel);
    part.check(`${tag}: each strip row is named in text`, state.stripRows.length >= 4 && state.stripRows.every((l) => /^[^:]+ \([^)]*\): |^Timber store to repair: |^Granary condition: /.test(l)),
      state.stripRows.join(" | "));
    await chainSection(page).getByLabel("Show every snapshot").check();
    // The turn table pages its rows: show them all.
    for (let more = chainSection(page).getByRole("button", { name: /^Show (the last \d+|\d+ more \(\d+ not shown\))$/ }); await more.count();) await more.click();
    state = await settled(page);
    part.check(`${tag}: "Show every snapshot" lists all ${x.list.length} snapshots`, state.rows.length === x.list.length
      && state.rows.map((r) => r.turn).join() === x.list.join(), `${state.rows.length}`);
    const repairCol = state.columns.indexOf(LINK.repair) - 1;
    const stalledRows = state.rows.filter((r) => /stalled: /.test(r.cells[repairCol] ?? "")).map((r) => r.turn);
    const expectedStalled = x.list.filter((t) => (R(t).stalls ?? []).length > 0);
    const runs = (state.stripRows.find((l) => l.startsWith(`${LINK.repair}: `)) ?? "").split("; ").flatMap((seg) => {
      const m = seg.match(/stalled, snapshots? (\d+)(?:-(\d+))?$/);
      if (!m) return [];
      const [a, b] = [Number(m[1]), Number(m[2] ?? m[1])];
      return Array.from({ length: b - a + 1 }, (_, i) => a + i);
    });
    part.check(`${tag}: the table's stalled snapshots are the bundle's (${expectedStalled.length})`, stalledRows.join() === expectedStalled.join(),
      `${stalledRows} vs ${expectedStalled}`);
    part.check(`${tag}: the strip's stalled runs are the table's stalled rows`, runs.join() === stalledRows.join(), `${runs} vs ${stalledRows}`);
    // A row's seek button moves the slider.
    await chainSection(page).getByRole("button", { name: `Seek to snapshot ${stall}`, exact: true }).click();
    await waitPlayhead(page, stall);
    state = await settled(page);
    part.check(`${tag}: the turn table's seek button moves the slider to ${stall}`, state.slider === String(stall) && state.heading === `${HEADING} · snapshot ${stall}`,
      `${state.slider} ${state.heading}`);
    const current = state.rows.find((r) => r.current);
    part.check(`${tag}: the current snapshot's row is marked`, current?.turn === stall, JSON.stringify(current?.turn));
    await chainSection(page).getByLabel("Show every snapshot").uncheck();
    // The region picker: another region and back.
    const other = (region + 1) % x.regions.length;
    state = await pickRegion(page, other);
    part.check(`${tag}: picking ${x.regions[other]} re-labels both tables`, state.nowLabel === `Recovery chain in ${x.regions[other]} at snapshot ${stall}`
      && state.overLabel === `Recovery chain in ${x.regions[other]} over snapshots`, `${state.nowLabel}; ${state.overLabel}`);
    checkValues(part, `${tag} ${x.regions[other]} T${stall}`, state, stall, x.regions[other], x.at(stall, other), x.on);
    state = await pickRegion(page, region);
    part.check(`${tag}: picking ${name} again restores its chain`, state.nowLabel === `Recovery chain in ${name} at snapshot ${stall}`, state.nowLabel);
    // A repair holding timber while the region's store held none (its delivery came after the hold): the view must
    // not attribute the hold to the store. The first such case in the run, wherever it is.
    const empty = x.list.flatMap((t) => x.regions.map((_, r) => [t, r])).find(([t, r]) => {
      const e = x.at(t, r);
      return e.store && e.store !== "none" && e.store.held <= 0 && (e.holders ?? []).length > 0;
    });
    if (empty) {
      const [t, r] = empty;
      await pickRegion(page, r);
      state = await seek(page, t);
      checkValues(part, `${tag} ${x.regions[r]} T${t} (store held nothing)`, state, t, x.regions[r], x.at(t, r), x.on);
      await pickRegion(page, region);
    } else part.notes.push(`${tag}: no repair held timber while its region's store held none in this run`);
    checkFits(part, `${tag} picker`, state, viewportName);
    part.errorsFree(viewportName);
    await context.close();
  }
}

const VARIANT_PY = String.raw`
import sys
from chronicler.bundle_codec import load_bundle, dumps_bundle
src, dst, a, b, c = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
x = load_bundle(src)
for s in x["history"]:
    l = s.get("livelihoods")
    if s["turn"] == a:
        l.pop("remittances", None)                    # on in the run, absent here: unknown
    elif s["turn"] == b:                              # this turn's frames blanked: unknown, not zero
        hr = l["household_retail"]
        hr["regions"] = hr["money"] = hr["income"] = hr["sample"] = hr["sample_dropped"] = None
        l["recovery_crews"]["receipts"] = l["recovery_crews"]["ledger"] = None
    elif s["turn"] == c:
        l["timber_supply"]["source_turn"] = c + 5     # misdated: rejected as malformed
open(dst, "w", encoding="utf-8").write(dumps_bundle(x))
`;

async function partVariant(browser, url, bundle, x) {
  const part = partLog("variant");
  const region = chainRegions(x)[0] ?? 0;
  const name = x.regions[region];
  const paid = x.list.find((t) => (x.at(t, region).pl3_wages ?? 0) > 0) ?? 20;
  const [a, b, c] = [paid - 1, paid, paid + 1];
  const variant = path.join(options.out, "constructed-unknown-and-malformed.json");
  const run = spawnSync(options.python, ["-c", VARIANT_PY, bundle, variant, String(a), String(b), String(c)], { env: process.env, encoding: "utf8" });
  if (run.status !== 0) throw new Error(`variant construction failed: ${run.stderr}`);
  part.notes.push(`constructed variant of ${bundle}: remittances removed at ${a}, retail frame and PL3 receipts blanked at ${b}, timber supply misdated at ${c}; ${variant}`);
  const { context, page } = await newPage(browser, "desktop", part, url);
  await loadBundle(page, variant, x.regions.length);
  await seek(page, 1);
  await pickRegion(page, region);
  let state = await seek(page, a);
  part.check(`T${a}: remittances on in the run but absent here say unknown, not zero`,
    state.links[LINK.remittances]?.what === "Unknown, not zero: no Remittances (RS4) record at this snapshot.", state.links[LINK.remittances]?.what);
  state = await seek(page, b);
  part.check(`T${b}: the blanked retail frame says unknown, not zero`, /^Unknown, not zero: the household retail frame/.test(state.links[LINK.retail]?.what ?? ""),
    state.links[LINK.retail]?.what);
  part.check(`T${b}: blanked PL3 receipts leave the region's wage total unknown`, /PL3 granary crews: Unknown, not zero/.test(state.links[LINK.wages]?.what ?? "")
    && /The region's total is unknown/.test(state.links[LINK.wages]?.what ?? "") && !/Total paid/.test(state.links[LINK.wages]?.what ?? ""), state.links[LINK.wages]?.what);
  const row = state.rows.find((r) => r.turn === b);
  part.check(`T${b}: the turn table claims no zero wage`, !!row && !/^0 coins/.test(row.cells[state.columns.indexOf(LINK.wages) - 1] ?? ""), JSON.stringify(row?.cells));
  part.check(`T${b}: the run's wage total reads "at least"`, state.notes.some((n) => / wages at least [\d,.]+ coins to /.test(n)),
    state.notes.find((n) => /over snapshots/.test(n)));
  part.check(`T${b}: the totals say what is unknown`, state.notes.some((n) => /Totals count known snapshots only; unknown at, wholly or in part: .*Wages paid \(PL3, RS2, PL1\) 2, Food purchases \(PL4\) 1, Remittances in \(RS4\) 1\./.test(n)),
    state.notes.find((n) => /over snapshots/.test(n)));
  await part.shot(chainSection(page), `desktop-variant-${name.replace(/\W+/g, "-")}-T${b}.jpg`);
  state = await seek(page, c);
  part.check(`T${c}: the misdated timber supply record is rejected as malformed`,
    state.links[LINK.expedition]?.what === "Unknown, rejected as malformed: the Timber supply (PL1) record was rejected: misdated observation.", state.links[LINK.expedition]?.what);
  state = await seek(page, c + 1);
  part.check(`T${c + 1}: the next snapshot reads normally`, !/^Unknown/.test(state.links[LINK.expedition]?.what ?? "Unknown")
    && !/^Unknown/.test(state.links[LINK.retail]?.what ?? "Unknown"), `${state.links[LINK.expedition]?.what} | ${state.links[LINK.retail]?.what}`);
  part.check("variant: no NaN or undefined", !BAD_TEXT.test(state.text));
  part.errorsFree("variant");
  await context.close();
}

async function partSubset(browser, url, bundle, x) {
  const part = partLog("subset");
  part.check("subset run: timber supply, timber stock and remittances are off; repair projects, crews and retail on",
    !x.on.timber_supply && !x.on.timber_stock && !x.on.remittances && x.on.repair_projects && x.on.recovery_crews && x.on.household_retail, JSON.stringify(x.on));
  const { context, page } = await newPage(browser, "desktop", part, url);
  await loadBundle(page, bundle, x.regions.length);
  const region = x.regions.map((_, r) => r).find((r) => x.list.some((t) => (x.at(t, r).pl3_wages ?? 0) > 0)) ?? 0;
  const turn = x.list.find((t) => (x.at(t, region).pl3_wages ?? 0) > 0) ?? x.total;
  await seek(page, 1);
  await pickRegion(page, region);
  const state = await seek(page, turn);
  part.check("the chain view mounts with only some switches on", state.mounted && state.heading === `${HEADING} · snapshot ${turn}`, state.heading);
  part.check("the off packages are named", state.notes.some((n) => /Off: Timber supply \(PL1\) \(--timber-supply\), Timber stock \(L3\) \(--timber-stock\), Remittances \(RS4\) \(--remittances\)/.test(n)),
    state.notes.find((n) => /^On in this run/.test(n)));
  checkValues(part, `${x.regions[region]} T${turn}`, state, turn, x.regions[region], x.at(turn, region), x.on);
  part.check("the turn table leaves the off links out", !state.columns.some((c) => [LINK.expedition, LINK.forest, LINK.store, LINK.remittances].includes(c))
    && state.columns.includes(LINK.wages), state.columns.join(" | "));
  part.check("the wages say the PL1 source is off", /PL1 woodcutters: off\./.test(state.links[LINK.wages]?.what ?? ""), state.links[LINK.wages]?.what);
  await part.shot(chainSection(page), `desktop-subset-T${turn}.jpg`);
  part.errorsFree("subset");
  await context.close();
}

function nativeIdentity() {
  const run = spawnSync(options.python, [path.join(REPO, "scripts", "check_python_env.py"), "--expect", "native"],
    { env: process.env, encoding: "utf8" });
  report.native = { exit: run.status, output: run.stdout.trim().split("\n") };
  if (run.status !== 0) throw new Error(`the native extension check failed:\n${run.stdout}\n${run.stderr}`);
}

/** Refuse an `--out` the script must not empty: the current directory, the repository or viewer/ or anything
 * holding them, anything inside the repository, or an existing directory this script did not create. */
function prepareOut(out) {
  const inside = (child, parent) => child === parent || child.startsWith(parent + path.sep);
  for (const [label, dir] of [["the current directory", process.cwd()], ["the repository", REPO], ["viewer/", VIEWER]]) {
    if (inside(dir, out)) throw new Error(`Refusing --out ${out}: it is or holds ${label} (${dir})`);
  }
  if (inside(out, REPO)) throw new Error(`Refusing --out ${out}: generated runs and screenshots stay outside the repository`);
  if (existsSync(out)) {
    if (!statSync(out).isDirectory()) throw new Error(`Refusing --out ${out}: not a directory`);
    if (readdirSync(out).length && !existsSync(path.join(out, MARKER)))
      throw new Error(`Refusing --out ${out}: an existing directory this script did not create (no ${MARKER}); use a new path`);
    rmSync(out, { recursive: true, force: true });
  }
  mkdirSync(out, { recursive: true });
  writeFileSync(path.join(out, MARKER), "Output of viewer/scripts/qa-recovery-chain.mjs; the next run empties this directory.\n");
}

async function main() {
  prepareOut(options.out);
  nativeIdentity();
  const { chromium } = loadPlaywright();
  const server = await serve(options.build);
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch();
  report.chromium = browser.version();
  try {
    let chain = null;
    let expected = null;
    for (const [name, run] of [["chain", partChain], ["variant", partVariant], ["subset", partSubset]]) {
      if (!options.parts.has(name)) continue;
      try {
        if (name === "subset") {
          const subset = simulate("subset", SUBSET);
          await run(browser, url, subset, expectations(subset));
        } else {
          chain ??= simulate("chain", CHAIN);
          expected ??= expectations(chain);
          await run(browser, url, chain, expected);
        }
      } catch (error) {
        const part = report.parts[name] ?? partLog(name);
        part.check(`${name}: the part completed`, false, String(error?.stack ?? error));
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  for (const [name, part] of Object.entries(report.parts)) {
    const passed = part.checks.filter((c) => c.ok).length;
    console.log(`${name}: ${passed}/${part.checks.length} checks; ${part.messages.length} console messages`);
    for (const message of part.messages) console.log(`   console: ${message}`);
  }
  report.failures = failures;
  writeFileSync(path.join(options.out, "report.json"), `${JSON.stringify(report, (key, value) => typeof value === "function" ? undefined : value, 2)}\n`);
  console.log(`${failures === 0 ? "all checks passed" : `${failures} checks failed`}; report in ${options.out}`);
  process.exitCode = failures === 0 ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
