#!/usr/bin/env node
/**
 * Browser QA of the household retail panel (L6b, `--household-retail`) on the
 * Livelihoods tab, its feature options in the live setup form and Batch Lab,
 * and Batch Lab cancellation, on a production build in headless Chromium
 * (Playwright; `require("playwright")`). Opt-in, not CI. Modelled on
 * qa-productive-recovery.mjs.
 *
 *   PYTHONPATH=../src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
 *   node scripts/qa-household-retail.mjs [--build dist] --out DIR \
 *     --bundle FILE [--bundle FILE ...] [--old-bundle FILE ...] \
 *     [--python python3] [--parts bundles,old,live,batch]
 *
 * `--bundle` names runs with `--food-allocation --household-retail` in any
 * mode and boundary (the panel must label each); `--old-bundle` runs without
 * the key (written before retail existed, or with it off). `--python` must
 * import `chronicler` (set PYTHONPATH) and, for the live parts, the native
 * extension. Parts:
 *
 * - bundles: at 1440x900 and 390x844 (touch), each `--bundle` is opened with
 *   "Open saved world file" and the Livelihoods tab is seeked with the
 *   "Historical turn" slider (End, PageDown, Home, ArrowRight twice, a click
 *   on the track, ArrowLeft). At each stop the "Household retail" section must
 *   be mounted and readable (not "rejected as malformed"); its heading's
 *   "snapshot N" and every table it labels must name the slider's turn, its
 *   first note must name simulation turn N - 1, and its mode and boundary must
 *   be the run's, labelled plainly. The expected record of each turn is read
 *   from the bundle with `--python` (`chronicler.bundle_codec`): when anyone
 *   was priced out, short of the offer or short of a withheld claim, the
 *   people-at-risk sentence and table must name them, children first; when
 *   nobody was, the sentence must say everyone reached their fair share. The
 *   food and money tables have one row per pilot region (the would-be table
 *   in record_only). No "NaN" or "undefined" anywhere in the systems panel
 *   (every tab is read at the last turn); at 390 px no horizontal page
 *   overflow.
 * - old: each `--old-bundle` shows no household retail section and its food
 *   allocation section, seeking forward and back. A constructed variant of
 *   the first `--bundle` (made with `--python`, written to `--out`, labelled
 *   constructed): turns 1-20 without the record, 21-25 with it malformed in
 *   five ways (the owned food does not close, misdated, a provisioning column
 *   dropped, the money rows off, an unknown mode), 31-35 with the turn's
 *   frame blanked to null (missing data), 36-38 with the record null, 41-43
 *   with no livelihoods record, 46 with an unknown livelihoods schema, 47-48
 *   with the counters blanked. Absent records mount no section, malformed
 *   ones say "rejected as malformed" with no table, blanked frames say
 *   "unknown, not zero" with only the lifetime table, and nothing crashes,
 *   also when rewinding through them.
 * - live: `--live --live-port 0 --simulate-only --agents hybrid --pause-every
 *   5` (cwd `--out/live`). The setup form must list `--household-retail`
 *   unchecked and disabled until `--food-allocation`, its mode and boundary
 *   hidden until it is checked, defaults marked, and dropping food allocation
 *   must drop all three. A 20-turn world (template seed 7, 4 civs, 8 regions)
 *   runs with food allocation and household retail, boundary `all`. At the
 *   pause at turn 5 the Livelihoods tab is checked through "Inspect world
 *   while paused", rewound to turn 3 and forward again, then Save checkpoint,
 *   Fork and Quit. `--live --resume <checkpoint>` must show the same tab at
 *   turn 5 and date it 10 after Continue. The Fork hint's command (`--fork
 *   <state.json> --seed 9 --turns 5`, a development seed) runs and its bundle
 *   is opened: the section must read and be dated.
 * - batch: a second live session (cwd `--out/batch`); Batch Lab lists the
 *   switch unchecked; `--agents off` disables it with the runs' mode named. A
 *   one-seed batch (template seed 7, a development seed, 120 turns, one
 *   worker) with food allocation and household retail (free_exchange,
 *   paid_work) is started and cancelled: Run Batch returns with no error
 *   banner, the options are kept, and the batch manifest records the switch,
 *   its mode and boundary. Batch Lab stops between seeds and every seed
 *   neighbouring a template development seed is held or unlisted, so the
 *   cancel lands after the only seed; the manifest's status is recorded, not
 *   required to be cancelled. A second batch starts and cancels. No overflow
 *   at 390 px.
 *
 * Console errors and page errors fail a part. `--out` is emptied first;
 * `report.json`, screenshots (JPEG), the variant, the sessions' logs and
 * outputs go there. Exits 1 when a check fails.
 */
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".json": "application/json", ".wasm": "application/wasm",
};
const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 } },
  phone: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};
const RETAIL = "Household retail";
const FOOD = "Food allocation";
const HEADINGS = [RETAIL, FOOD];
/** The modes and boundaries as the panel labels them. */
const MODE_LABEL = {
  retail: "Mode: retail.", no_relief: "Mode: no_relief (what relief protects).",
  free_exchange: "Mode: free_exchange (ownership without cash).", record_only: "Mode: record_only (identity control, nothing applied).",
};
const MODE_NOTE = {
  retail: /^Simulation turn \d+\. Retail: /, no_relief: /^Simulation turn \d+\. No-relief control \(what relief protects\)/,
  free_exchange: /^Simulation turn \d+\. Free-exchange control \(ownership without cash\)/,
  record_only: /^Simulation turn \d+\. Record-only control \(identity control, nothing applied\)/,
};
const BOUNDARY_LABEL = { market: "Pilot boundary: market:", paid_work: "Pilot boundary: paid_work:", all: "Pilot boundary: all:" };
const RISK_SHORT = { priced_out: "priced out", offer_short: "offer short", withheld_dead: "withheld for heirs" };
const MALFORMED = /rejected as malformed/;
const UNKNOWN = /^The retail frame of simulation turn \d+ was not recorded: .* unknown, not zero\.$/;
const BAD_TEXT = /\bNaN\b|\bundefined\b/;
/** A development world (template seed 7). */
const WORLD = { seed: "7", turns: "20", civs: "4", regions: "8" };

function parseArgs(argv) {
  const options = { build: path.join(HERE, "..", "dist"), out: null, bundles: [], old: [], python: "python3",
    parts: "bundles,old,live,batch" };
  for (let index = 0; index < argv.length; index += 2) {
    const [flag, value] = [argv[index], argv[index + 1]];
    if (value === undefined) throw new Error(`${flag} needs a value`);
    if (flag === "--build") options.build = path.resolve(value);
    else if (flag === "--out") options.out = path.resolve(value);
    else if (flag === "--bundle") options.bundles.push(path.resolve(value));
    else if (flag === "--old-bundle") options.old.push(path.resolve(value));
    else if (flag === "--python") options.python = value;
    else if (flag === "--parts") options.parts = value;
    else throw new Error(`Unknown option ${flag}`);
  }
  options.parts = new Set(options.parts.split(",").filter(Boolean));
  if (!options.out || ((options.parts.has("bundles") || options.parts.has("old")) && options.bundles.length === 0)) {
    throw new Error("Usage: qa-household-retail.mjs --out DIR --bundle FILE [--bundle FILE] [--old-bundle FILE] "
      + "[--python PY] [--build DIR] [--parts bundles,old,live,batch]");
  }
  return options;
}

const options = parseArgs(process.argv.slice(2));
const report = { generated: new Date().toISOString(), build: options.build, parts: {} };
const sessions = [];
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

/** A part's check list, console/page error capture and screenshots. */
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
  part.shot = async (page, file, locator = null) => {
    const target = path.join(options.out, file);
    if (locator) await locator.screenshot({ path: target, type: "jpeg", quality: 55, scale: "css", animations: "disabled" });
    else await page.screenshot({ path: target, type: "jpeg", quality: 55, scale: "css", animations: "disabled" });
    part.screenshots.push(target);
  };
  part.errorsFree = (label) => {
    const errors = part.messages.filter((m) => / (pageerror|error):/.test(m));
    part.check(`${label}: no console or page errors`, errors.length === 0, errors.join(" | "));
  };
  return part;
}

/** In the page: what the systems panel shows (the active tab's sections and notes). */
function readSystems(headings) {
  const shell = document.querySelector(".systems-shell");
  const panel = shell?.querySelector('[role="tabpanel"]') ?? null;
  const sections = panel ? [...panel.querySelectorAll("section")] : [];
  const panels = {};
  for (const heading of headings) {
    const section = sections.find((s) => {
      const text = s.querySelector("h3")?.textContent ?? "";
      return text === heading || text.startsWith(`${heading} · `);
    });
    panels[heading] = section ? {
      heading: section.querySelector("h3").textContent,
      notes: [...section.querySelectorAll(".systems-note")].map((n) => n.textContent),
      tables: [...section.querySelectorAll("table")].map((t) => ({
        label: t.getAttribute("aria-label") ?? "", rows: t.querySelectorAll("tbody tr").length,
        first: t.querySelector("tbody tr")?.textContent ?? "" })),
    } : null;
  }
  return {
    panels,
    tab: panel?.getAttribute("aria-label") ?? null,
    tabs: shell ? [...shell.querySelectorAll('[role="tab"]')].map((t) => t.textContent) : [],
    headings: panel ? [...panel.querySelectorAll("h3")].map((h) => h.textContent) : [],
    bodyNotes: panel ? [...panel.querySelectorAll(".systems-body > p.systems-note")].map((n) => n.textContent) : [],
    text: shell?.innerText ?? "",
    playhead: document.querySelector(".phase75-playhead-label")?.textContent ?? null,
    slider: document.querySelector('[role="slider"]')?.getAttribute("aria-valuenow") ?? null,
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  };
}

/** The systems panel once its text is the same over two double frames. */
async function settled(page) {
  let previous = null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const current = await page.evaluate(readSystems, HEADINGS);
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
}

async function openLivelihoods(page) {
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

// ---------------------------------------------------------------- expectations read from a bundle

const EXPECT_PY = String.raw`
import json, sys
from chronicler.bundle_codec import load_bundle
b = load_bundle(sys.argv[1])
RISKS = ("priced_out", "offer_short", "withheld_dead")
out = {}
for s in b["history"]:
    l = s.get("livelihoods") or {}
    x = l.get("household_retail") if isinstance(l, dict) else None
    if not isinstance(x, dict):
        out[s["turn"]] = None
        continue
    regions = x.get("regions")
    rows = [r["provisioning"] for r in regions or [] if r.get("provisioning")]
    risk = {k: [int(sum(p[k + "_children"] for p in rows)), int(sum(p[k + "_persons"] for p in rows)),
                int(sum(p[k + "_households"] for p in rows))] for k in RISKS}
    out[s["turn"]] = {"mode": x["mode"], "boundary": x["boundary"], "regions": None if regions is None else len(regions),
                      "provisioned": len(rows), "risk": risk,
                      "at_risk_regions": sum(1 for p in rows if any(p[k + "_persons"] for k in RISKS))}
json.dump({"regions": len(b["world_state"]["regions"]), "total": b["metadata"]["total_turns"], "turns": out}, sys.stdout)
`;

function expectations(file) {
  const run = spawnSync(options.python, ["-c", EXPECT_PY, file], { env: process.env, encoding: "utf8", maxBuffer: 1 << 26 });
  if (run.status !== 0) throw new Error(`reading ${file} failed: ${run.stderr}`);
  return JSON.parse(run.stdout);
}

const plural = (n, one, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

/** The household retail section shows the record of the slider's turn. */
function checkRetail(part, tag, state, turn, expected) {
  part.check(`${tag}: slider and playhead at T${turn}`, state.slider === String(turn) && state.playhead === `T${turn}`,
    `${state.slider} ${state.playhead}`);
  const shown = state.panels[RETAIL];
  if (expected === null) {
    part.check(`${tag}: no household retail section without a record`, shown === null, shown?.heading);
    return;
  }
  if (!shown) { part.check(`${tag}: ${RETAIL} mounted`, false, state.headings.join(" | ")); return; }
  part.check(`${tag}: ${RETAIL} readable (not rejected as malformed)`, !shown.notes.some((n) => MALFORMED.test(n)),
    shown.notes.find((n) => MALFORMED.test(n)));
  const snapshot = Number(shown.heading.match(/· snapshot (\d+)$/)?.[1]);
  const source = Number((shown.notes[0] ?? "").match(/^Simulation turn (\d+)\./)?.[1]);
  const dated = shown.tables.map((t) => t.label.match(/(?:at|to) snapshot (\d+)$/)?.[1]).filter(Boolean).map(Number);
  part.check(`${tag}: ${RETAIL} is dated snapshot ${turn} (source turn ${turn - 1})`,
    snapshot === turn && source === turn - 1 && dated.length === shown.tables.length && dated.every((n) => n === turn),
    `${shown.heading}; ${shown.notes[0]?.slice(0, 60)}; tables ${dated.join(",")}`);
  part.check(`${tag}: the mode (${expected.mode}) and boundary (${expected.boundary}) are labelled plainly`,
    MODE_NOTE[expected.mode].test(shown.notes[0] ?? "") && (shown.notes[1] ?? "").startsWith(MODE_LABEL[expected.mode])
    && (shown.notes[1] ?? "").includes(BOUNDARY_LABEL[expected.boundary]), `${shown.notes[0]?.slice(0, 80)} | ${shown.notes[1]?.slice(0, 80)}`);
  const table = (prefix) => shown.tables.find((t) => t.label.startsWith(prefix));
  if (expected.regions === null) {
    part.check(`${tag}: an unrecorded frame says unknown, with no this-turn table`, shown.notes.some((n) => UNKNOWN.test(n))
      && shown.tables.length === 1 && shown.tables[0].label.startsWith("Household retail to snapshot"), JSON.stringify(shown.tables));
  } else if (expected.regions === 0) {
    part.check(`${tag}: no pilot region is said`, shown.notes.some((n) => /^No region is in the pilot at simulation turn/.test(n)));
  } else if (expected.mode === "record_only") {
    part.check(`${tag}: record-only shows the would-be title, one row per pilot region, and no provisioning`,
      table("Would-be retail at snapshot")?.rows === expected.regions && !table("Owned food at") && !table("People below"),
      JSON.stringify(shown.tables));
  } else {
    part.check(`${tag}: one owned-food and one money row per pilot region (${expected.regions})`,
      table("Owned food at snapshot")?.rows === expected.regions && table("Food money at snapshot")?.rows === expected.regions,
      JSON.stringify(shown.tables));
    const sentence = shown.notes.find((n) => / were provisioned in /.test(n)) ?? "";
    const below = Object.entries(expected.risk).filter(([, v]) => v[1] > 0);
    if (expected.provisioned === 0) {
      part.check(`${tag}: nobody provisioned is said`, shown.notes.some((n) => n === "No pilot region was provisioned this turn."));
    } else if (below.length === 0) {
      part.check(`${tag}: everyone reached their fair share, and no risk table`, sentence.endsWith("Everyone reached their fair share.")
        && !table("People below their fair share"), sentence);
    } else {
      const parts = below.map(([k, [children, persons, households]]) =>
        `${RISK_SHORT[k]}, ${plural(children, "child", "children")} among ${plural(persons, "person", "people")} in ${plural(households, "household")}`);
      part.check(`${tag}: the people at risk are named, children first (${parts.join("; ")})`,
        parts.every((p) => sentence.includes(p)) && table("People below their fair share at snapshot")?.rows === expected.at_risk_regions,
        `${sentence} | ${JSON.stringify(shown.tables.map((t) => [t.label, t.rows]))}`);
    }
  }
  part.check(`${tag}: no NaN or undefined in the systems panel`, !BAD_TEXT.test(state.text), state.text.match(/.{0,60}(NaN|undefined).{0,60}/)?.[0]);
}

function checkFits(part, tag, state, viewportName) {
  if (viewportName !== "phone") return;
  part.check(`${tag}: no horizontal page overflow`, state.scrollWidth <= state.innerWidth + 1, `${state.scrollWidth} > ${state.innerWidth}`);
}

async function newPage(browser, viewportName, part) {
  const context = await browser.newContext(VIEWPORTS[viewportName]);
  const page = await context.newPage();
  part.watch(page, viewportName);
  return { context, page };
}

// ---------------------------------------------------------------- bundles

async function partBundles(browser, url) {
  const part = partLog("bundles");
  const expected = new Map(options.bundles.map((file) => [file, expectations(file)]));
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForSelector(".phase75-shell");
    for (const file of options.bundles) {
      const label = path.basename(path.dirname(file));
      const tag = `${viewportName} ${label}`;
      const want = expected.get(file);
      const total = want.total;
      await loadBundle(page, file, want.regions);
      await openLivelihoods(page);
      const slider = page.getByRole("slider", { name: "Historical turn" });
      await slider.focus();
      const at = (state, stop, turn) => checkRetail(part, `${tag} ${stop}`, state, turn, want.turns[turn]);

      await slider.press("End");
      await waitPlayhead(page, total);
      let state = await settled(page);
      at(state, "End", total);
      checkFits(part, `${tag} End`, state, viewportName);
      const tab = page.locator('.systems-shell [role="tabpanel"]');
      await part.shot(page, `${viewportName}-${label}-retail-T${total}.jpg`, page.locator("section[aria-label='Household retail']"));

      await slider.press("PageDown");
      await waitPlayhead(page, total - 10);
      state = await settled(page);
      at(state, "PageDown", total - 10);

      await slider.press("Home");
      await waitPlayhead(page, 1);
      state = await settled(page);
      at(state, "Home", 1);
      checkFits(part, `${tag} Home`, state, viewportName);

      await slider.press("ArrowRight");
      await slider.press("ArrowRight");
      await waitPlayhead(page, 3);
      state = await settled(page);
      at(state, "ArrowRight x2", 3);

      await slider.scrollIntoViewIfNeeded();
      const track = await slider.boundingBox();
      await page.mouse.click(track.x + track.width / 2, track.y + track.height / 2);
      await page.waitForFunction(() => document.querySelector(".phase75-playhead-label")?.textContent !== "T3", null, { timeout: 10000 });
      state = await settled(page);
      const clicked = Number(state.slider);
      part.check(`${tag} track click seeks near the middle`, Math.abs(clicked - (Math.round(0.5 * (total - 1)) + 1)) <= 2, `T${clicked}`);
      at(state, "track click", clicked);
      if (viewportName === "phone") await part.shot(page, `${viewportName}-${label}-livelihoods-T${clicked}.jpg`, tab);

      await slider.focus();
      await slider.press("ArrowLeft");
      await waitPlayhead(page, clicked - 1);
      state = await settled(page);
      at(state, "ArrowLeft", clicked - 1);
      checkFits(part, `${tag} track`, state, viewportName);

      // The turn with the most people at risk, if any (seeked with keys).
      const risky = Object.entries(want.turns).filter(([, e]) => e && e.provisioned)
        .map(([t, e]) => [Number(t), Object.values(e.risk).reduce((a, v) => a + v[1], 0)]).sort((a, b) => b[1] - a[1] || a[0] - b[0])[0];
      if (risky && risky[1] > 0) {
        state = await seek(page, risky[0]);
        at(state, "most at risk", risky[0]);
        checkFits(part, `${tag} most at risk`, state, viewportName);
        await part.shot(page, `${viewportName}-${label}-retail-T${risky[0]}-at-risk.jpg`, page.locator("section[aria-label='Household retail']"));
      }
      part.notes.push(`${tag}: most people below their fair share at ${risky ? `T${risky[0]} (${risky[1]})` : "no turn"}`);

      await slider.focus();
      await slider.press("End");
      await waitPlayhead(page, total);
      const bad = [];
      for (const name of (await settled(page)).tabs) {
        await page.getByRole("tab", { name, exact: true }).click();
        const shown = await settled(page);
        if (BAD_TEXT.test(shown.text)) bad.push(`${name}: ${shown.text.match(/.{0,50}(NaN|undefined).{0,50}/)?.[0]}`);
        if (viewportName === "phone" && shown.scrollWidth > shown.innerWidth + 1) bad.push(`${name}: overflow ${shown.scrollWidth}`);
      }
      part.check(`${tag}: every systems tab at T${total} free of NaN/undefined${viewportName === "phone" ? " and overflow" : ""}`,
        bad.length === 0, bad.join(" | "));
      await openLivelihoods(page);
    }
    part.errorsFree(viewportName);
    await context.close();
  }
}

// ---------------------------------------------------------------- old bundles, constructed variant (missing data)

const VARIANT_PY = String.raw`
import sys
from chronicler.bundle_codec import load_bundle, dumps_bundle
src, dst = sys.argv[1], sys.argv[2]
b = load_bundle(src)
for s in b["history"]:
    t, l = s["turn"], s.get("livelihoods")
    if not isinstance(l, dict) or not isinstance(l.get("household_retail"), dict):
        continue
    x = l["household_retail"]
    provisioned = [r for r in x["regions"] or [] if r.get("provisioning")]
    if t <= 20:                      # before the record exists
        l.pop("household_retail")
    elif t == 21:                    # the owned food does not close
        x["regions"][0]["flows"]["titled"] = x["regions"][0]["flows"].get("titled", 0) + 7
    elif t == 22:                    # misdated
        x["source_turn"] = t + 5
    elif t == 23:                    # a provisioning column dropped
        provisioned[0]["provisioning"].pop("priced_out_children")
    elif t == 24:                    # the money rows do not match the regions
        x["money"]["paid_milli"] += 1
        x["money"]["credited_milli"] += 1
    elif t == 25:                    # an unknown mode
        x["mode"] = "barter"
    elif 31 <= t <= 35:              # this turn's frame blanked to null (missing data)
        for k in ("regions", "money", "income", "sample", "sample_dropped"):
            x[k] = None
    elif 36 <= t <= 38:              # the record blanked
        l["household_retail"] = None
    elif 41 <= t <= 43:              # no livelihoods record
        s["livelihoods"] = None
    elif t == 46:                    # unknown livelihoods schema
        l["schema_version"] = 99
    elif t in (47, 48):              # counters blanked
        x["counters"] = None
open(dst, "w", encoding="utf-8").write(dumps_bundle(b))
`;

const MALFORMED_REASON = {
  21: /the owned food does not close/, 22: /misdated observation/, 23: /malformed provisioning row/,
  24: /money rows differ from the region totals/, 25: /unknown household-retail schema/, 47: /malformed counters/,
  48: /malformed counters/,
};

function buildVariant(source, target) {
  const run = spawnSync(options.python, ["-c", VARIANT_PY, source, target], { env: process.env, encoding: "utf8", maxBuffer: 1 << 26 });
  if (run.status !== 0) throw new Error(`variant construction failed: ${run.stderr}`);
}

/** Expectations at a turn of the constructed variant. */
function checkVariant(part, tag, state, turn, natural) {
  part.check(`${tag}: no NaN or undefined`, !BAD_TEXT.test(state.text), state.text.match(/.{0,60}(NaN|undefined).{0,60}/)?.[0]);
  const shown = state.panels[RETAIL];
  if (turn <= 20 || (turn >= 36 && turn <= 38)) {
    part.check(`${tag}: no record, no household retail section; food allocation still shown`, shown === null
      && state.headings.includes(`${FOOD} · snapshot ${turn}`), state.headings.join(" | "));
  } else if (MALFORMED_REASON[turn]) {
    part.check(`${tag}: a malformed record says so, undated, with no table`, shown !== null && shown.heading === RETAIL
      && shown.tables.length === 0 && shown.notes.length === 1 && MALFORMED.test(shown.notes[0]) && shown.notes[0].includes(`snapshot ${turn}`)
      && MALFORMED_REASON[turn].test(shown.notes[0]), JSON.stringify(shown));
  } else if (turn >= 31 && turn <= 35) {
    part.check(`${tag}: a blanked frame is dated and says unknown, with only the lifetime table`, shown !== null
      && shown.heading === `${RETAIL} · snapshot ${turn}` && shown.notes.some((n) => UNKNOWN.test(n))
      && shown.tables.length === 1 && shown.tables[0].label === `Household retail to snapshot ${turn}`
      && !shown.notes.some((n) => /were provisioned|Everyone reached|No region is in the pilot/.test(n)),
    shown ? `${shown.heading}; ${shown.tables.map((t) => t.label).join(",")}` : "not mounted");
  } else if (turn >= 41 && turn <= 43) {
    part.check(`${tag}: no livelihoods record is said, nothing mounted`, shown === null
      && state.bodyNotes.includes(`No livelihoods observation is recorded at snapshot ${turn}.`), JSON.stringify(state.bodyNotes));
  } else if (turn === 46) {
    part.check(`${tag}: an unknown livelihoods schema is refused as unreadable`,
      state.bodyNotes.some((n) => n.startsWith(`The livelihoods record at snapshot ${turn} is unreadable`)), JSON.stringify(state.bodyNotes));
  } else {
    checkRetail(part, tag, state, turn, natural.turns[turn]);
  }
}

async function partOld(browser, url) {
  const part = partLog("old");
  const variant = path.join(options.out, "constructed-missing-data.json");
  buildVariant(options.bundles[0], variant);
  const natural = expectations(options.bundles[0]);
  part.notes.push(`constructed variant of ${options.bundles[0]}: ${variant}`);
  const variantTurns = [1, 20, 21, 22, 23, 24, 25, 31, 35, 36, 41, 43, 46, 47, 50, natural.total];
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForSelector(".phase75-shell");
    for (const old of options.old) {
      const tag = `${viewportName} old ${path.basename(path.dirname(old))}`;
      const raw = JSON.parse(readFileSync(old, "utf8"));
      await loadBundle(page, old, raw.world_state.regions.length);
      await openLivelihoods(page);
      const total = raw.metadata.total_turns;
      for (const turn of [total, 1, Math.round(total / 2), total - 1]) {
        const state = await seek(page, turn);
        part.check(`${tag} T${turn}: no household retail section`, state.panels[RETAIL] === null
          && !state.headings.some((h) => h.startsWith(RETAIL)), state.headings.join(" | "));
        part.check(`${tag} T${turn}: food allocation read and dated`, state.panels[FOOD]?.heading === `${FOOD} · snapshot ${turn}`,
          state.headings.join(" | "));
        part.check(`${tag} T${turn}: no NaN or undefined`, !BAD_TEXT.test(state.text));
        checkFits(part, `${tag} T${turn}`, state, viewportName);
        if (turn === total) await part.shot(page, `${viewportName}-old-${path.basename(path.dirname(old))}-T${turn}.jpg`, page.locator('.systems-shell [role="tabpanel"]'));
      }
    }
    {
      const tag = `${viewportName} constructed`;
      const raw = JSON.parse(readFileSync(variant, "utf8"));
      await loadBundle(page, variant, raw.world_state.regions.length);
      await openLivelihoods(page);
      for (const turn of variantTurns.filter((t) => t <= raw.metadata.total_turns)) {
        const state = await seek(page, turn);
        checkVariant(part, `${tag} T${turn}`, state, turn, natural);
        checkFits(part, `${tag} T${turn}`, state, viewportName);
        if (turn === 21 || turn === 31) await part.shot(page, `${viewportName}-constructed-T${turn}.jpg`, page.locator('.systems-shell [role="tabpanel"]'));
      }
      for (const turn of [35, 22, 12, 37, 50]) {           // rewind and step through blanked, malformed and absent turns
        const state = await seek(page, turn);
        checkVariant(part, `${tag} rewind T${turn}`, state, turn, natural);
      }
    }
    part.errorsFree(viewportName);
    await context.close();
  }
}

// ---------------------------------------------------------------- live sessions

function liveSession(label, args, origin) {
  const dir = path.join(options.out, label);
  mkdirSync(dir, { recursive: true });
  const child = spawn(options.python, ["-u", "-m", "chronicler.main", "--live", "--live-port", "0", "--simulate-only",
    "--agents", "hybrid", "--live-origin", origin, ...args,
    "--output", path.join(dir, "chronicle.md"), "--state", path.join(dir, "state.json")],
  { cwd: dir, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
  const session = { label, dir, child, log: "", link: null };
  sessions.push(session);
  const log = createWriteStream(path.join(options.out, `${label}.log`));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label}: no viewer link`)), 120000);
    const read = (chunk) => {
      log.write(chunk);
      session.log += chunk.toString();
      const match = session.log.match(/Open viewer: (\S+)/);
      if (match && !session.link) {
        session.link = `${origin}/${new URL(match[1]).search}`;
        clearTimeout(timer);
        resolve(session);
      }
    };
    child.stdout.on("data", read);
    child.stderr.on("data", read);
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (!session.link) reject(new Error(`${label} exited (${code}) before printing a link`));
    });
  });
}

function exited(session, ms = 60000) {
  if (session.child.exitCode !== null) return Promise.resolve(session.child.exitCode);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), ms);
    session.child.on("exit", (code) => { clearTimeout(timer); resolve(code); });
  });
}

const box = (page, label, flag) => page.getByRole("checkbox", { name: `${label} ${flag}`, exact: true });
const retailBox = (page) => box(page, "Household retail", "--household-retail");
const foodBox = (page) => box(page, "Food allocation", "--food-allocation");
const MODE = "Household retail mode --household-retail-mode";
const BOUNDARY = "Household retail boundary --household-retail-boundary";
/** A control's description (its help and its "Needs"/"Unavailable" line). */
const described = (locator) => locator.evaluate((element) => (element.getAttribute("aria-describedby") ?? "").split(" ")
  .map((id) => document.getElementById(id)?.textContent ?? "").join(" "));

async function expandFeatures(page) {
  const toggle = page.getByRole("button", { name: /Experimental features \(off by default\)/ });
  await toggle.waitFor({ timeout: 30000 });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  return toggle;
}

/** The switch is listed, unchecked, its mode and boundary selects hidden. */
async function checkDefaults(part, page, tag) {
  const control = retailBox(page);
  part.check(`${tag}: household retail offered, unchecked`, (await control.count()) === 1 && !(await control.isChecked()));
  part.check(`${tag}: its mode and boundary hidden while off`, (await page.getByRole("combobox", { name: MODE, exact: true }).count()) === 0
    && (await page.getByRole("combobox", { name: BOUNDARY, exact: true }).count()) === 0);
}

const optionTexts = (select) => select.locator("option").allTextContents().then((t) => t.join("|"), () => "missing");

async function liveSetup(part, page) {
  const tag = "setup form";
  await expandFeatures(page);
  await checkDefaults(part, page, tag);
  const retail = retailBox(page);
  const food = foodBox(page);
  const why = await described(retail);
  part.notes.push(`setup reason with nothing selected: ${why}`);
  part.check(`${tag}: household retail disabled, naming --food-allocation`, await retail.isDisabled()
    && /Unavailable: requires --food-allocation\./.test(why), why);
  await food.check();
  part.check(`${tag}: food allocation enables household retail`, await retail.isEnabled());
  await retail.check();
  const mode = page.getByRole("combobox", { name: MODE, exact: true });
  const boundary = page.getByRole("combobox", { name: BOUNDARY, exact: true });
  part.check(`${tag}: mode choices shown, retail the default`, (await mode.count()) === 1 && (await mode.inputValue()) === "retail"
    && (await optionTexts(mode)) === "retail (default)|no_relief|free_exchange|record_only", await optionTexts(mode));
  part.check(`${tag}: boundary choices shown, market the default`, (await boundary.count()) === 1 && (await boundary.inputValue()) === "market"
    && (await optionTexts(boundary)) === "market (default)|paid_work|all", await optionTexts(boundary));
  await food.uncheck();
  part.check(`${tag}: dropping food allocation drops household retail and its options`, !(await retail.isChecked())
    && await retail.isDisabled() && (await mode.count()) === 0 && (await boundary.count()) === 0);
  // The world's selection: food allocation and household retail, boundary all.
  await food.check();
  await retail.check();
  await boundary.selectOption("all");
  const summary = await page.locator("section[aria-label='Experimental features'] [aria-live=polite]").innerText();
  part.notes.push(`setup summary: ${summary}`);
  part.check(`${tag}: summary lists the selected flags, not the default mode`, ["--food-allocation", "--household-retail",
    "--household-retail-boundary=all"].every((flag) => summary.includes(flag)) && !summary.includes("--household-retail-mode"), summary);
}

/** In a live session: the retail section of a paused turn (a natural record, boundary all, retail mode). */
function checkLive(part, tag, state, turn) {
  checkRetail(part, tag, state, turn, liveExpect(state));
  part.check(`${tag}: food allocation mounted beside it`, state.panels[FOOD]?.heading === `${FOOD} · snapshot ${turn}`, state.headings.join(" | "));
}

/** What a live turn must show: retail mode, boundary all, a recorded frame (the region counts are read from the page). */
function liveExpect(state) {
  const shown = state.panels[RETAIL];
  const food = shown?.tables.find((t) => t.label.startsWith("Owned food at snapshot"));
  const risk = shown?.tables.find((t) => t.label.startsWith("People below their fair share at snapshot"));
  const sentence = shown?.notes.find((n) => / were provisioned in /.test(n)) ?? "";
  const counts = { priced_out: null, offer_short: null, withheld_dead: null };
  for (const k of Object.keys(counts)) {
    const m = sentence.match(new RegExp(`${RISK_SHORT[k]}, ([\\d,]+) (?:child|children) among ([\\d,]+) (?:person|people) in ([\\d,]+) household`));
    counts[k] = m ? m.slice(1, 4).map((v) => Number(v.replace(/,/g, ""))) : [0, 0, 0];
  }
  return { mode: "retail", boundary: "all", regions: food?.rows ?? -1, provisioned: food?.rows ?? 0, risk: counts,
    at_risk_regions: risk?.rows ?? 0 };
}

/** Paused: the Livelihoods tab, rewound to an earlier turn and back. */
async function rewindWhilePaused(part, page, turn, back) {
  await page.getByRole("button", { name: "Inspect world while paused" }).click();
  await page.getByRole("button", { name: "Return to run controls" }).waitFor({ timeout: 20000 });
  const active = await page.locator(".phase75-mode-tab.active").first().textContent();
  if (active !== "Overview") await page.locator(".phase75-mode-tab", { hasText: /^Overview$/ }).first().click();
  await page.waitForSelector(".systems-shell [role=tab]", { timeout: 60000 });
  await openLivelihoods(page);
  const slider = page.getByRole("slider", { name: "Historical turn" });
  await slider.focus();
  for (let i = 0; i < turn - back; i += 1) await slider.press("ArrowLeft");
  await waitPlayhead(page, back);
  let state = await settled(page);
  checkLive(part, `live rewind T${back}`, state, back);
  for (let i = 0; i < turn - back; i += 1) await slider.press("ArrowRight");
  await waitPlayhead(page, turn);
  state = await settled(page);
  checkLive(part, `live forward again T${turn}`, state, turn);
  await page.getByRole("button", { name: "Return to run controls" }).click();
  await page.getByRole("dialog", { name: `Paused simulation at turn ${turn}` }).waitFor({ timeout: 20000 });
}

async function livelihoodsAt(part, page, turn, shot = null) {
  await page.getByRole("button", { name: "Inspect world while paused" }).click();
  await page.getByRole("button", { name: "Return to run controls" }).waitFor({ timeout: 20000 });
  const active = await page.locator(".phase75-mode-tab.active").first().textContent();
  if (active !== "Overview") await page.locator(".phase75-mode-tab", { hasText: /^Overview$/ }).first().click();
  await page.waitForSelector(".systems-shell [role=tab]", { timeout: 60000 });
  await openLivelihoods(page);
  await page.waitForFunction((value) => document.querySelector(".phase75-playhead-label")?.textContent === value, `T${turn}`, { timeout: 30000 })
    .catch(() => {});
  const state = await settled(page);
  if (shot) await part.shot(page, shot, page.locator('.systems-shell [role="tabpanel"]'));
  await page.getByRole("button", { name: "Return to run controls" }).click();
  await page.getByRole("dialog", { name: `Paused simulation at turn ${turn}` }).waitFor({ timeout: 20000 });
  return state;
}

function firstDifference(a, b) {
  let index = 0;
  while (index < a.length && a[index] === b[index]) index += 1;
  return index === a.length && index === b.length ? "" : `at ${index}: ${JSON.stringify(a.slice(index, index + 80))} vs ${JSON.stringify(b.slice(index, index + 80))}`;
}

async function partLive(browser, origin) {
  const part = partLog("live");
  let forkState = null;
  const context = await browser.newContext(VIEWPORTS.desktop);
  const page = await context.newPage();
  part.watch(page, "first");
  const first = await liveSession("live", ["--pause-every", "5"], origin);
  await page.goto(first.link);
  await page.getByRole("button", { name: "Run World" }).waitFor({ timeout: 60000 });
  await page.getByLabel("Seed").fill(WORLD.seed);
  await page.getByLabel("Turns").fill(WORLD.turns);
  await page.getByLabel("Civilizations").fill(WORLD.civs);
  await page.getByLabel("Regions").fill(WORLD.regions);
  await liveSetup(part, page);
  await part.shot(page, "live-setup-features.jpg", page.locator("section[aria-label='Experimental features']"));
  await page.getByRole("button", { name: "Run World" }).click();
  await page.getByRole("heading", { name: "Paused at Turn 5" }).waitFor({ timeout: 300000 });
  const before = await livelihoodsAt(part, page, 5, "live-livelihoods-T5.jpg");
  checkLive(part, "live T5", before, 5);
  part.notes.push(`live T5 retail notes: ${(before.panels[RETAIL]?.notes ?? []).slice(2, 3).join(" | ")}`);
  await rewindWhilePaused(part, page, 5, 3);

  await page.getByRole("button", { name: "Save checkpoint" }).click();
  const saved = page.getByRole("status").filter({ hasText: "Checkpoint saved at turn 5" });
  await saved.waitFor({ timeout: 60000 });
  const checkpoint = await saved.locator("code").innerText();
  part.check("live: checkpoint saved on disk", existsSync(checkpoint), checkpoint);
  await page.getByRole("button", { name: "Fork" }).click();
  const forked = page.getByText("Fork saved to:").locator("..");
  await forked.waitFor({ timeout: 60000 });
  const forkText = (await forked.innerText()).replace(/\s+/g, " ").trim();
  part.notes.push(`Fork printed: ${forkText}`);
  part.check("live: Fork prints a state-file path and a --fork hint", /--fork \S+state\.json --seed SEED --turns TURNS/.test(forkText), forkText);
  forkState = forkText.match(/--fork (\S+state\.json)/)?.[1];
  part.check("live: the fork state file exists", !!forkState && existsSync(forkState), forkState);
  await page.getByRole("button", { name: "Quit" }).click();
  part.check("live: the first session ends after Quit", (await exited(first)) === 0, `exit ${first.child.exitCode}`);
  await page.close();

  const resumed = await liveSession("resumed", ["--resume", checkpoint], origin);
  const page2 = await context.newPage();
  part.watch(page2, "resumed");
  await page2.goto(resumed.link);
  await page2.getByRole("heading", { name: "Paused at Turn 5" }).waitFor({ timeout: 300000 });
  const after = await livelihoodsAt(part, page2, 5, "resumed-livelihoods-T5.jpg");
  checkLive(part, "resumed T5", after, 5);
  const panelText = (state) => state.text.slice(state.text.indexOf(state.headings[0] ?? "\u0000"));
  part.check("resumed: the Livelihoods tab matches the paused session at turn 5", panelText(after) === panelText(before)
    && JSON.stringify(after.panels) === JSON.stringify(before.panels), firstDifference(panelText(before), panelText(after)));
  await page2.getByRole("button", { name: "Continue" }).click();
  await page2.getByRole("heading", { name: "Paused at Turn 10" }).waitFor({ timeout: 300000 });
  const later = await livelihoodsAt(part, page2, 10, "resumed-livelihoods-T10.jpg");
  checkLive(part, "resumed T10", later, 10);
  await page2.getByRole("button", { name: "Quit" }).click();
  part.check("resumed: the session ends after Quit", (await exited(resumed)) === 0, `exit ${resumed.child.exitCode}`);
  part.check("live: no traceback in the session logs", !/Traceback/.test(first.log + resumed.log));
  if (forkState && existsSync(forkState)) await forkFromState(part, context, origin, forkState);
  part.errorsFree("live");
  await context.close();
}

/** The Fork hint's command with a development seed: a state file rebuilds the native pool. */
async function forkFromState(part, context, origin, forkState) {
  const dir = path.join(options.out, "fork-cli");
  mkdirSync(dir, { recursive: true });
  const run = spawnSync(options.python, ["-m", "chronicler.main", "--fork", forkState, "--seed", "9", "--turns", "5",
    "--simulate-only", "--agents", "hybrid", "--output", path.join(dir, "chronicle.md"), "--state", path.join(dir, "state.json")],
  { cwd: dir, env: process.env, encoding: "utf8", timeout: 300000 });
  writeFileSync(path.join(options.out, "fork-cli.log"), `${run.stdout ?? ""}${run.stderr ?? ""}`);
  const file = path.join(dir, "chronicle_bundle.json");
  part.check("fork: `--fork <state.json> --seed 9 --turns 5` completes", run.status === 0 && existsSync(file), (run.stderr ?? "").slice(-300));
  if (!existsSync(file)) return;
  const want = expectations(file);
  const page = await context.newPage();
  part.watch(page, "fork");
  await page.goto(`${origin}/`, { waitUntil: "load" });
  await page.waitForSelector(".phase75-shell");
  await loadBundle(page, file, want.regions);
  await openLivelihoods(page);
  const turns = Object.keys(want.turns).map(Number).sort((a, b) => a - b);
  part.notes.push(`fork bundle: snapshots ${turns[0]}-${turns.at(-1)}`);
  for (const turn of [turns.at(-1), turns[0]]) {
    const state = await seek(page, turn);
    checkRetail(part, `fork T${turn}`, state, turn, want.turns[turn]);
    const records = state.panels[RETAIL]?.notes.find((n) => /^Recent pilot records|^Records this turn/.test(n));
    part.notes.push(`fork T${turn} retail records: ${records ?? "none"}`);
  }
  await page.close();
}

async function partBatch(browser, origin) {
  const part = partLog("batch");
  const context = await browser.newContext(VIEWPORTS.desktop);
  const page = await context.newPage();
  part.watch(page, "batch");
  const session = await liveSession("batch", [], origin);
  await page.goto(session.link);
  await page.getByRole("button", { name: "Run World" }).waitFor({ timeout: 60000 });
  await page.locator(".phase75-mode-tab", { hasText: /^Batch Lab$/ }).first().click();
  await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 30000 });
  await expandFeatures(page);
  await checkDefaults(part, page, "Batch Lab");
  const agents = page.getByRole("combobox", { name: /Agent mode for these runs/ });
  part.check("Batch Lab: agent mode select offered", (await agents.count()) === 1);
  const retail = retailBox(page);
  const food = foodBox(page);
  await food.check();
  part.check("Batch Lab: food allocation enables household retail", await retail.isEnabled());
  await agents.selectOption("off");
  const why = await described(retail);
  part.check("Batch Lab: --agents off drops food allocation and disables household retail with the runs' mode named",
    !(await food.isChecked()) && await retail.isDisabled() && /requires --agents hybrid \(these runs use --agents off\)/.test(why), why);
  await agents.selectOption("");
  const field = (label) => page.locator("label", { hasText: new RegExp(`^${label.replace(/[()]/g, "\\$&")}$`) }).locator("xpath=following-sibling::input");
  // One development seed (template 7): Batch Lab runs consecutive seeds, and no two template development seeds are consecutive.
  await field("Start Seed").fill("7");
  await field("Seed Count").fill("1");
  await field("Turns").fill("120");
  await field("Workers (0 = auto)").fill("1");
  await food.check();
  await retail.check();
  await page.getByRole("combobox", { name: MODE, exact: true }).selectOption("free_exchange");
  await page.getByRole("combobox", { name: BOUNDARY, exact: true }).selectOption("paid_work");
  await page.setViewportSize(VIEWPORTS.phone.viewport);
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  part.check("Batch Lab: no horizontal overflow at 390 px with the options open", fits);
  await part.shot(page, "batch-lab-phone.jpg", page.locator("section[aria-label='Experimental features']"));
  await page.setViewportSize(VIEWPORTS.desktop.viewport);
  await page.getByRole("button", { name: /Run Batch/ }).click();
  const cancel = page.getByRole("button", { name: "Cancel Batch" });
  await cancel.waitFor({ timeout: 30000 });
  part.check("Batch Lab: options locked while running", await retail.isDisabled() && await food.isDisabled());
  await cancel.click();
  const returned = await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 300000 }).then(() => true, () => false);
  part.check("Batch Lab: Cancel returns to Run Batch", returned);
  part.check("Batch Lab: no error banner after cancel", (await page.locator(".bg-red-900\\/50").count()) === 0,
    await page.locator(".bg-red-900\\/50").allInnerTexts().then((t) => t.join(" | ")));
  part.check("Batch Lab: options enabled again, selection kept", await retail.isEnabled() && await retail.isChecked() && await food.isChecked()
    && (await page.getByRole("combobox", { name: MODE, exact: true }).inputValue()) === "free_exchange"
    && (await page.getByRole("combobox", { name: BOUNDARY, exact: true }).inputValue()) === "paid_work");
  const manifests = [];
  const walk = (dir) => { for (const name of existsSync(dir) ? readdirSync(dir) : []) {
    const entry = path.join(dir, name);
    if (name === "batch_manifest.json") manifests.push(entry);
    else if (statSync(entry).isDirectory() && !name.startsWith("seed_")) walk(entry);
  } };
  walk(path.join(session.dir, "output"));
  const manifest = manifests.length === 1 ? JSON.parse(readFileSync(manifests[0], "utf8")) : null;
  const config = manifest?.simulation ?? {};
  const recorded = { food_allocation: config.food_allocation, household_retail: config.household_retail,
    household_retail_mode: config.household_retail_mode, household_retail_boundary: config.household_retail_boundary };
  const seeds = manifest?.runs?.map((r) => r.seed);
  part.notes.push(`batch manifest ${manifests[0] ?? "missing"}: status ${manifest?.status}, seeds ${JSON.stringify(seeds)}, `
    + `${manifest?.runs?.filter((r) => r.total_turns !== null).length} completed; agents ${config.agents}; ${JSON.stringify(recorded)}`);
  part.check("Batch Lab: the batch manifest records the switch, its mode and boundary, for development seed 7 only", manifest !== null
    && ["cancelled", "complete", "completed"].includes(manifest.status) && JSON.stringify(seeds) === "[7]" && config.agents === "hybrid"
    && JSON.stringify(recorded) === JSON.stringify({ food_allocation: true, household_retail: true,
      household_retail_mode: "free_exchange", household_retail_boundary: "paid_work" }),
  `${manifests.length} manifests; ${manifest?.status}; ${JSON.stringify(seeds)}; ${JSON.stringify(recorded)}`);
  await part.shot(page, "batch-lab-after-cancel.jpg");
  await page.getByRole("button", { name: /Run Batch/ }).click();
  await cancel.waitFor({ timeout: 30000 });
  await cancel.click();
  part.check("Batch Lab: a second batch can be started and cancelled",
    await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 300000 }).then(() => true, () => false));
  await page.locator(".phase75-mode-tab", { hasText: /^Setup$/ }).first().click();
  await expandFeatures(page);
  part.check("Batch Lab: the setup form's options are unaffected by the batch", (await retailBox(page).count()) === 1
    && !(await retailBox(page).isChecked()));
  part.check("batch: no traceback in the session log", !/Traceback/.test(session.log), session.log.match(/Traceback[\s\S]{0,400}/)?.[0]);
  part.errorsFree("batch");
  await context.close();
}

async function main() {
  rmSync(options.out, { recursive: true, force: true });
  mkdirSync(options.out, { recursive: true });
  const { chromium } = require("playwright");
  const server = await serve(options.build);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  report.chromium = browser.version();
  try {
    for (const [name, run] of [["bundles", partBundles], ["old", partOld], ["live", partLive], ["batch", partBatch]]) {
      if (!options.parts.has(name)) continue;
      try {
        await run(browser, name === "live" || name === "batch" ? origin : `${origin}/`);
      } catch (error) {
        const part = report.parts[name] ?? partLog(name);
        part.check(`${name}: the part completed`, false, String(error?.stack ?? error));
      }
    }
  } finally {
    await browser.close();
    server.close();
    for (const session of sessions) {
      if (session.child.exitCode === null) {
        session.child.kill();
        await exited(session, 10000);
      }
    }
  }
  for (const [name, part] of Object.entries(report.parts)) {
    const passed = part.checks.filter((c) => c.ok).length;
    console.log(`${name}: ${passed}/${part.checks.length} checks; ${part.messages.length} console messages`);
    for (const message of part.messages) console.log(`   console: ${message}`);
  }
  report.sessions = sessions.map((s) => ({ label: s.label, pid: s.child.pid, exit: s.child.exitCode }));
  report.failures = failures;
  writeFileSync(path.join(options.out, "report.json"), `${JSON.stringify(report, (key, value) => typeof value === "function" ? undefined : value, 2)}\n`);
  console.log(`${failures === 0 ? "all checks passed" : `${failures} checks failed`}; report in ${options.out}`);
  process.exitCode = failures === 0 ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
