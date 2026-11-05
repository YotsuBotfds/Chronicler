#!/usr/bin/env node
/**
 * Browser QA of the recovery-skills panels on the Livelihoods tab, the
 * recovery-skills feature options and Batch Lab cancellation, on a production
 * build in headless Chromium (Playwright; `require("playwright")`). Opt-in,
 * not CI.
 *
 *   PYTHONPATH=../src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
 *   node scripts/qa-recovery-skills.mjs [--build dist] --out DIR \
 *     --bundle RS_BUNDLE [--bundle RS_BUNDLE ...] \
 *     [--workshops-bundle FILE] [--off-bundle FILE] [--python python3] \
 *     [--parts bundles,old,live,batch]
 *
 * `--bundle` names runs with every recovery-skills switch on;
 * `--workshops-bundle` a run with workshops and no recovery-skills package;
 * `--off-bundle` a run with no livelihoods record. `--python` must import
 * `chronicler` (set PYTHONPATH) and, for the live parts, the native
 * extension (`--agents hybrid`). The build is served on 127.0.0.1 and the
 * live sessions are started with `--live-origin` for it. Parts:
 *
 * - bundles: at 1440x900 and 390x844 (touch), loads each `--bundle` with
 *   "Open saved world file", opens the Livelihoods tab and seeks with the
 *   "Historical turn" slider (End, PageDown, Home, ArrowRight twice, a
 *   click on the track, ArrowLeft). At each stop the five panels (Workshop
 *   apprenticeship, Repair projects, Veterans, Remittances and diaspora,
 *   Clearing protection) must be mounted, each heading's "snapshot N" and
 *   every table it labels must name the slider's turn, and its first note
 *   must name simulation turn N - 1 (the record's source turn). No "NaN" or
 *   "undefined" in the systems panel (every tab is read at the last turn);
 *   at 390 px no horizontal page overflow. Screenshots of the tab.
 * - old: the workshops bundle shows its workshop panel and none of the five
 *   headings; the off bundle has no Livelihoods tab. A constructed variant
 *   of the first `--bundle` (made with `--python` and
 *   `chronicler.bundle_codec`, written to `--out`, labelled constructed in
 *   the report): turns 1-20 without the five records, 21-25 with each
 *   record malformed, 31-35 with this turn's frame blanked to null, 41-43
 *   with no livelihoods record and 46 with an unknown livelihoods schema.
 *   Absent records mount no panel, malformed ones say "not observed",
 *   "unavailable" or "rejected" with no table, blanked frames say "unknown,
 *   not zero" (or "not empty") with no this-turn table, and nothing crashes.
 * - live: starts `--live --live-port 0 --simulate-only --agents hybrid
 *   --pause-every 5` (cwd `--out/live`) and opens its link: the setup
 *   form's experimental section must list the five switches unchecked,
 *   their mode selects hidden until checked and each disabled, naming its
 *   unmet prerequisites, until they are met (apprenticeship: workshops;
 *   repair projects: workshops or grain storage; veterans: workshops,
 *   apprenticeship or repair projects); dropping a prerequisite drops its
 *   dependants. It launches a 20-turn world (seed 42, 4 civs, 8 regions)
 *   with workshops and all five switches (clearing protection in its
 *   cost_only mode). At the pause at turn 5 it opens the Livelihoods tab
 *   through "Inspect world while paused" (the pause dialog covers the page)
 *   and checks the panels, then "Return to run controls", Save checkpoint,
 *   Fork (records what it prints) and Quit. `--live --resume <checkpoint>`
 *   must show the same Livelihoods tab at turn 5 and date it 10 after
 *   Continue. Last, the Fork hint's command (`--fork <state.json> --seed 43
 *   --turns 5`, cwd `--out/fork-cli`) runs and its bundle is opened: the
 *   state file rebuilds the native pool, so remittances must report the
 *   rebuild and veteran records close with reason pool_reset.
 * - batch: a second live session (cwd `--out/batch`); Batch Lab must show
 *   the five switches unchecked, and `--agents off` must disable
 *   remittances. It starts a 3-seed, 10-turn, 1-worker batch with workshops
 *   and remittances, cancels it and checks the panel returns to Run Batch
 *   with no error banner, the options enabled and still selected, and the
 *   batch manifest (`output/batch_gui_<time>/batch_<n>/batch_manifest.json`)
 *   cancelled with the switches recorded; a second batch starts and
 *   cancels the same way. The section must not overflow at 390 px. The
 *   lobby has no Quit control, so the session is stopped by its PID.
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
/** The five recovery-skills panels: heading, its source-turn note and its "unknown this turn" wording. */
const PANELS = [
  { key: "apprenticeship", heading: "Workshop apprenticeship", label: "Apprenticeship", flag: "--apprenticeship",
    mode: "Apprenticeship mode --apprenticeship-mode", source: /^Simulation turn (\d+)\./,
    unknown: /continuity this turn is unknown, not zero/, thisTurn: ["Apprenticeship sites at snapshot"] },
  { key: "repair_projects", heading: "Repair projects", label: "Repair projects", flag: "--repair-projects",
    mode: "Repair mode --repair-mode", source: /^Simulation turn (\d+)\./,
    unknown: /this turn's work, crews and spending are unknown, not zero/, thisTurn: ["Repair accounts at snapshot"] },
  { key: "veteran_reintegration", heading: "Veterans", label: "Veteran reintegration", flag: "--veteran-reintegration",
    mode: "Veteran mode --veteran-mode", source: /^Simulation turn (\d+)\./,
    unknown: /releases, placements and waiting are unknown, not zero/, thisTurn: ["Veterans this turn at snapshot"] },
  { key: "remittances", heading: "Remittances and diaspora", label: "Remittances", flag: "--remittances",
    mode: "Remittance mode --remittance-mode", source: /^Simulation turn (\d+)\./,
    unknown: /senders, amounts and the diaspora are unknown, not zero/,
    thisTurn: ["Remittances at snapshot", "Diaspora by region at snapshot", "Unmet senders at snapshot"] },
  { key: "clearing_protection", heading: "Clearing protection", label: "Clearing protection", flag: "--clearing-protection",
    mode: "Clearing protection mode --clearing-protection-mode", source: /^Phase 9 of simulation turn (\d+)\./,
    unknown: /this turn's protection accounts are unknown, not empty/,
    thisTurn: ["Protected regions at snapshot", "Cover kept and lost at snapshot", "Unmet needs at snapshot"] },
];
const HEADINGS = PANELS.map((p) => p.heading);
const NOT_OBSERVED = /not observed|unavailable|rejected as malformed/;
const BAD_TEXT = /\bNaN\b|\bundefined\b/;
const WORLD = { seed: "42", turns: "20", civs: "4", regions: "8" };

function parseArgs(argv) {
  const options = { build: path.join(HERE, "..", "dist"), out: null, bundles: [], workshops: null, off: null,
    python: "python3", parts: "bundles,old,live,batch" };
  for (let index = 0; index < argv.length; index += 2) {
    const [flag, value] = [argv[index], argv[index + 1]];
    if (value === undefined) throw new Error(`${flag} needs a value`);
    if (flag === "--build") options.build = path.resolve(value);
    else if (flag === "--out") options.out = path.resolve(value);
    else if (flag === "--bundle") options.bundles.push(path.resolve(value));
    else if (flag === "--workshops-bundle") options.workshops = path.resolve(value);
    else if (flag === "--off-bundle") options.off = path.resolve(value);
    else if (flag === "--python") options.python = value;
    else if (flag === "--parts") options.parts = value;
    else throw new Error(`Unknown option ${flag}`);
  }
  options.parts = new Set(options.parts.split(",").filter(Boolean));
  if (!options.out || ((options.parts.has("bundles") || options.parts.has("old")) && options.bundles.length === 0)) {
    throw new Error("Usage: qa-recovery-skills.mjs --out DIR --bundle FILE [--bundle FILE] [--workshops-bundle FILE] "
      + "[--off-bundle FILE] [--python PY] [--build DIR] [--parts bundles,old,live,batch]");
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
      tables: [...section.querySelectorAll("table")].map((t) => t.getAttribute("aria-label") ?? ""),
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

/** The five panels show the record of the slider's turn (natural bundle). */
function checkDated(part, tag, state, turn) {
  part.check(`${tag}: slider and playhead at T${turn}`, state.slider === String(turn) && state.playhead === `T${turn}`,
    `${state.slider} ${state.playhead}`);
  for (const spec of PANELS) {
    const shown = state.panels[spec.heading];
    if (!shown) { part.check(`${tag}: ${spec.heading} mounted`, false, state.headings.join(" | ")); continue; }
    const snapshot = Number(shown.heading.match(/· snapshot (\d+)$/)?.[1]);
    const source = Number((shown.notes[0] ?? "").match(spec.source)?.[1]);
    const dated = shown.tables.map((label) => label.match(/(?:at|to) snapshot (\d+)$/)?.[1]).filter(Boolean).map(Number);
    part.check(`${tag}: ${spec.heading} is dated snapshot ${turn} (source turn ${turn - 1})`,
      snapshot === turn && source === turn - 1 && dated.length > 0 && dated.every((n) => n === turn),
      `${shown.heading}; ${shown.notes[0]?.slice(0, 60)}; tables ${dated.join(",")}`);
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
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForSelector(".phase75-shell");
    for (const file of options.bundles) {
      const label = path.basename(path.dirname(file));
      const tag = `${viewportName} ${label}`;
      const raw = JSON.parse(readFileSync(file, "utf8"));
      const total = raw.metadata.total_turns;
      await loadBundle(page, file, raw.world_state.regions.length);
      await openLivelihoods(page);
      const slider = page.getByRole("slider", { name: "Historical turn" });
      await slider.focus();

      await slider.press("End");
      await waitPlayhead(page, total);
      let state = await settled(page);
      checkDated(part, `${tag} End`, state, total);
      checkFits(part, `${tag} End`, state, viewportName);
      const tab = page.locator('.systems-shell [role="tabpanel"]');
      await part.shot(page, `${viewportName}-${label}-livelihoods-T${total}.jpg`, tab);

      await slider.press("PageDown");
      await waitPlayhead(page, total - 10);
      state = await settled(page);
      checkDated(part, `${tag} PageDown`, state, total - 10);
      part.check(`${tag} PageDown: the panels re-dated`, !state.headings.some((h) => h.endsWith(`snapshot ${total}`)), state.headings.join(" | "));

      await slider.press("Home");
      await waitPlayhead(page, 1);
      state = await settled(page);
      checkDated(part, `${tag} Home`, state, 1);
      checkFits(part, `${tag} Home`, state, viewportName);

      await slider.press("ArrowRight");
      await slider.press("ArrowRight");
      await waitPlayhead(page, 3);
      state = await settled(page);
      checkDated(part, `${tag} ArrowRight x2`, state, 3);

      // The tab sits below the map: bring the track back into view to click it.
      await slider.scrollIntoViewIfNeeded();
      const track = await slider.boundingBox();
      await page.mouse.click(track.x + track.width / 2, track.y + track.height / 2);
      await page.waitForFunction(() => document.querySelector(".phase75-playhead-label")?.textContent !== "T3", null, { timeout: 10000 });
      state = await settled(page);
      const clicked = Number(state.slider);
      part.check(`${tag} track click seeks near the middle`, Math.abs(clicked - (Math.round(0.5 * (total - 1)) + 1)) <= 2, `T${clicked}`);
      checkDated(part, `${tag} track click`, state, clicked);

      await slider.focus();
      await slider.press("ArrowLeft");
      await waitPlayhead(page, clicked - 1);
      state = await settled(page);
      checkDated(part, `${tag} ArrowLeft`, state, clicked - 1);
      checkFits(part, `${tag} track`, state, viewportName);

      // Every other systems tab at the last turn: no NaN or undefined.
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
      part.notes.push(`${tag}: ${state.tabs.length} systems tabs read at T${total}`);
    }
    part.errorsFree(viewportName);
    await context.close();
  }
}

// ---------------------------------------------------------------- old bundles, constructed variant

const VARIANT_PY = String.raw`
import sys
from chronicler.bundle_codec import load_bundle, dumps_bundle
src, dst = sys.argv[1], sys.argv[2]
b = load_bundle(src)
RS = ["apprenticeship", "repair_projects", "veteran_reintegration", "remittances", "clearing_protection"]
OBS = ["funnel", "totals", "regions", "moves", "moves_dropped", "closures", "closures_dropped",
       "receipts", "receipts_dropped", "unmet", "unmet_dropped"]
for s in b["history"]:
    t, l = s["turn"], s.get("livelihoods")
    if not isinstance(l, dict):
        continue
    if t <= 20:                      # before any record exists
        for k in RS:
            l.pop(k, None)
    elif 21 <= t <= 25:              # each record malformed
        l["apprenticeship"]["source_turn"] = t + 5
        l["repair_projects"]["units"] = None
        l["veteran_reintegration"]["mode"] = "bogus"
        l["remittances"]["counters"] = "n/a"
        l["clearing_protection"]["completed_turn"] = t + 1
    elif 31 <= t <= 35:              # this turn's frame blanked to null
        l["apprenticeship"]["continuity"] = None
        l["apprenticeship"]["receipts"] = None
        l["repair_projects"]["receipts"] = None
        l["repair_projects"]["ledger"] = None
        l["veteran_reintegration"]["frame"] = None
        for k in OBS:
            l["remittances"][k] = None
        c = l["clearing_protection"]
        c["observed"], c["receipts"], c["decisions"], c["unprotected"] = False, None, None, None
    elif 41 <= t <= 43:              # no livelihoods record
        s["livelihoods"] = None
    elif t == 46:                    # unknown livelihoods schema
        l["schema_version"] = 99
open(dst, "w", encoding="utf-8").write(dumps_bundle(b))
`;

function buildVariant(source, target) {
  const run = spawnSync(options.python, ["-c", VARIANT_PY, source, target], { env: process.env, encoding: "utf8" });
  if (run.status !== 0) throw new Error(`variant construction failed: ${run.stderr}`);
}

/** Expectations at a turn of the constructed variant. */
function checkVariant(part, tag, state, turn) {
  part.check(`${tag}: no NaN or undefined`, !BAD_TEXT.test(state.text), state.text.match(/.{0,60}(NaN|undefined).{0,60}/)?.[0]);
  const shown = PANELS.map((spec) => [spec, state.panels[spec.heading]]);
  if (turn <= 20) {
    part.check(`${tag}: before any record, no recovery-skills panel is mounted`, shown.every(([, s]) => s === null), state.headings.join(" | "));
    part.check(`${tag}: the workshop panel still shows snapshot ${turn}`, state.headings.includes(`Public workshops · snapshot ${turn}`), state.headings.join(" | "));
    part.check(`${tag}: no recovery-skills snapshot is claimed`, !state.headings.some((h) => HEADINGS.some((x) => h.startsWith(x))));
  } else if (turn <= 25) {
    for (const [spec, s] of shown) {
      part.check(`${tag}: malformed ${spec.heading} says so, undated, with no table`,
        s !== null && s.heading === spec.heading && s.tables.length === 0 && s.notes.length === 1 && NOT_OBSERVED.test(s.notes[0])
        && s.notes[0].includes(`snapshot ${turn}`), JSON.stringify(s));
    }
  } else if (turn >= 31 && turn <= 35) {
    for (const [spec, s] of shown) {
      const thisTurn = s ? s.tables.filter((label) => spec.thisTurn.some((prefix) => label.startsWith(prefix))) : [];
      part.check(`${tag}: blanked ${spec.heading} is dated and says unknown, with no this-turn table`,
        s !== null && s.heading === `${spec.heading} · snapshot ${turn}` && s.notes.some((n) => spec.unknown.test(n)) && thisTurn.length === 0,
        s ? `${s.heading}; ${thisTurn.join(",")}; ${s.notes.find((n) => /unknown/.test(n)) ?? "no unknown note"}` : "not mounted");
    }
    const sentinel = state.panels["Remittances and diaspora"];
    part.check(`${tag}: blanked remittances list no zero this-turn line`, sentinel !== null
      && !sentinel.notes.some((n) => /^No remittance this turn|^This turn:/.test(n)), JSON.stringify(sentinel?.notes));
    const clear = state.panels["Clearing protection"];
    part.check(`${tag}: blanked clearing protection claims no empty turn`, clear !== null
      && !clear.notes.some((n) => /^No region is protected this turn|^No controlled region was cleared/.test(n)), JSON.stringify(clear?.notes));
  } else if (turn >= 41 && turn <= 43) {
    part.check(`${tag}: no livelihoods record is said, nothing mounted`, shown.every(([, s]) => s === null)
      && state.bodyNotes.includes(`No livelihoods observation is recorded at snapshot ${turn}.`), JSON.stringify(state.bodyNotes));
  } else if (turn === 46) {
    part.check(`${tag}: an unknown livelihoods schema is refused as unreadable`,
      state.bodyNotes.some((n) => n.startsWith(`The livelihoods record at snapshot ${turn} is unreadable`)), JSON.stringify(state.bodyNotes));
  } else {
    checkDated(part, tag, state, turn);
  }
}

async function partOld(browser, url) {
  const part = partLog("old");
  const variant = path.join(options.out, "constructed-missing-rs.json");
  buildVariant(options.bundles[0], variant);
  part.notes.push(`constructed variant of ${options.bundles[0]}: ${variant}`);
  const variantTurns = [1, 20, 21, 25, 31, 35, 41, 43, 46, 50, 200];
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForSelector(".phase75-shell");

    if (options.workshops) {
      const tag = `${viewportName} ${path.basename(path.dirname(options.workshops))}`;
      const raw = JSON.parse(readFileSync(options.workshops, "utf8"));
      await loadBundle(page, options.workshops, raw.world_state.regions.length);
      await openLivelihoods(page);
      for (const turn of [raw.metadata.total_turns, 1]) {
        const state = await seek(page, turn);
        part.check(`${tag} T${turn}: workshop panel shown`, state.headings.includes(`Public workshops · snapshot ${turn}`), state.headings.join(" | "));
        part.check(`${tag} T${turn}: none of the five recovery-skills headings`, !state.headings.some((h) => HEADINGS.some((x) => h.startsWith(x))),
          state.headings.join(" | "));
        part.check(`${tag} T${turn}: no NaN or undefined`, !BAD_TEXT.test(state.text));
        checkFits(part, `${tag} T${turn}`, state, viewportName);
      }
    }
    if (options.off) {
      const tag = `${viewportName} ${path.basename(path.dirname(options.off))}`;
      const raw = JSON.parse(readFileSync(options.off, "utf8"));
      await loadBundle(page, options.off, raw.world_state.regions.length);
      const state = await settled(page);
      part.check(`${tag}: no Livelihoods tab`, !state.tabs.includes("Livelihoods"), state.tabs.join(","));
      part.check(`${tag}: no recovery-skills heading anywhere`, !(await page.locator("h3").allTextContents()).some((h) => HEADINGS.some((x) => h.startsWith(x))));
      checkFits(part, tag, state, viewportName);
    }
    {
      const tag = `${viewportName} constructed`;
      const raw = JSON.parse(readFileSync(variant, "utf8"));
      await loadBundle(page, variant, raw.world_state.regions.length);
      await openLivelihoods(page);
      for (const turn of variantTurns) {
        const state = await seek(page, turn);
        checkVariant(part, `${tag} T${turn}`, state, turn);
        checkFits(part, `${tag} T${turn}`, state, viewportName);
        if (turn === 21 || turn === 31) await part.shot(page, `${viewportName}-constructed-T${turn}.jpg`, page.locator('.systems-shell [role="tabpanel"]'));
      }
      // Rewind from a blanked turn into the malformed and absent ones.
      for (const turn of [35, 22, 12]) {
        const state = await seek(page, turn);
        checkVariant(part, `${tag} rewind T${turn}`, state, turn);
      }
      await part.shot(page, `${viewportName}-constructed-T12.jpg`, page.locator('.systems-shell [role="tabpanel"]'));
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

const box = (page, panel) => page.getByRole("checkbox", { name: `${panel.label} ${panel.flag}`, exact: true });
const prereq = (page, label, flag) => page.getByRole("checkbox", { name: `${label} ${flag}`, exact: true });
/** A control's description (its help and its "Needs"/"Unavailable" line). */
const described = (locator) => locator.evaluate((element) => (element.getAttribute("aria-describedby") ?? "").split(" ")
  .map((id) => document.getElementById(id)?.textContent ?? "").join(" "));

async function expandFeatures(page) {
  const toggle = page.getByRole("button", { name: /Experimental features \(off by default\)/ });
  await toggle.waitFor({ timeout: 30000 });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  return toggle;
}

/** The five switches are listed, unchecked, mode selects hidden. */
async function checkDefaults(part, page, tag) {
  for (const panel of PANELS) {
    const control = box(page, panel);
    part.check(`${tag}: ${panel.label} offered, unchecked`, (await control.count()) === 1 && !(await control.isChecked()));
    part.check(`${tag}: ${panel.label} mode hidden while off`,
      (await page.getByRole("combobox", { name: panel.mode, exact: true }).count()) === 0);
  }
}

async function liveSetup(part, page) {
  const tag = "setup form";
  await expandFeatures(page);
  await checkDefaults(part, page, tag);
  const [apprentice, repair, veterans, remit, clearing] = PANELS.map((panel) => box(page, panel));
  const workshops = prereq(page, "Workshops", "--workshops");
  const reserves = prereq(page, "Grain reserves", "--grain-reserves");
  const storage = prereq(page, "Grain storage", "--grain-storage");
  part.check(`${tag}: apprenticeship, repair projects and veterans disabled with nothing selected`,
    await apprentice.isDisabled() && await repair.isDisabled() && await veterans.isDisabled());
  part.check(`${tag}: remittances and clearing protection available (server runs hybrid)`,
    await remit.isEnabled() && await clearing.isEnabled());
  const why = [await described(apprentice), await described(repair), await described(veterans)];
  part.notes.push(`setup reasons with nothing selected: ${why.join(" / ")}`);
  part.check(`${tag}: each disabled switch names its unmet prerequisites`, /Unavailable: requires --workshops\./.test(why[0])
    && /Unavailable: requires one of: --workshops; --grain-storage\./.test(why[1])
    && /Unavailable: requires one of: --workshops; --apprenticeship; --repair-projects\./.test(why[2]), why.join(" / "));

  await workshops.check();
  part.check(`${tag}: workshops enables apprenticeship, repair projects, veterans`,
    await apprentice.isEnabled() && await repair.isEnabled() && await veterans.isEnabled());
  await apprentice.check();
  const mode = page.getByRole("combobox", { name: PANELS[0].mode, exact: true });
  part.check(`${tag}: apprenticeship mode select shown once checked, default train`,
    (await mode.count()) === 1 && (await mode.inputValue()) === "train");
  await repair.check();
  await workshops.uncheck();
  part.check(`${tag}: dropping workshops drops apprenticeship and repair projects`,
    !(await apprentice.isChecked()) && !(await repair.isChecked()) && await apprentice.isDisabled() && await repair.isDisabled()
    && (await mode.count()) === 0);
  await reserves.check();
  await storage.check();
  part.check(`${tag}: grain storage alone enables repair projects, not apprenticeship`, await repair.isEnabled() && await apprentice.isDisabled());
  await repair.check();
  part.check(`${tag}: repair projects alone enables veterans`, await veterans.isEnabled());
  await reserves.uncheck();
  part.check(`${tag}: dropping grain reserves drops storage, repair projects`, !(await storage.isChecked()) && !(await repair.isChecked()) && await veterans.isDisabled());

  // The world's selection: workshops and all five switches, clearing protection in its cost_only mode.
  await workshops.check();
  for (const control of [apprentice, repair, veterans, remit, clearing]) await control.check();
  for (const panel of PANELS) {
    part.check(`${tag}: ${panel.label} mode select shown when checked`, (await page.getByRole("combobox", { name: panel.mode, exact: true }).count()) === 1);
  }
  await page.getByRole("combobox", { name: PANELS[4].mode, exact: true }).selectOption("cost_only");
  const summary = await page.locator("section[aria-label='Experimental features'] [aria-live=polite]").innerText();
  part.notes.push(`setup summary: ${summary}`);
  part.check(`${tag}: summary lists the selected flags`, ["--workshops", "--apprenticeship", "--repair-projects", "--veteran-reintegration",
    "--remittances", "--clearing-protection", "--clearing-protection-mode=cost_only"].every((flag) => summary.includes(flag)), summary);
}

/** The Livelihoods tab while paused: "Inspect world while paused" hides the pause dialog. */
async function livelihoodsAt(part, page, turn, shot = null) {
  await page.getByRole("button", { name: "Inspect world while paused" }).click();
  await page.getByRole("button", { name: "Return to run controls" }).waitFor({ timeout: 20000 });
  // The shell's investigation surface hosts the systems panel.
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

function checkLive(part, tag, state, turn) {
  checkDated(part, tag, state, turn);
  const clearing = state.panels["Clearing protection"];
  part.check(`${tag}: clearing protection runs the requested cost_only mode`, !!clearing?.notes.some((n) => /Cost-only control/.test(n)),
    clearing?.notes[0]);
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
  await page.getByRole("heading", { name: "Paused at Turn 5" }).waitFor({ timeout: 180000 });
  const before = await livelihoodsAt(part, page, 5, "live-livelihoods-T5.jpg");
  checkLive(part, "live T5", before, 5);

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
  await page2.getByRole("heading", { name: "Paused at Turn 5" }).waitFor({ timeout: 180000 });
  const after = await livelihoodsAt(part, page2, 5, "resumed-livelihoods-T5.jpg");
  checkLive(part, "resumed T5", after, 5);
  const panelText = (state) => state.text.slice(state.text.indexOf(state.headings[0] ?? "\u0000"));
  part.check("resumed: the Livelihoods tab matches the paused session at turn 5", panelText(after) === panelText(before)
    && JSON.stringify(after.panels) === JSON.stringify(before.panels), firstDifference(panelText(before), panelText(after)));
  await page2.getByRole("button", { name: "Continue" }).click();
  await page2.getByRole("heading", { name: "Paused at Turn 10" }).waitFor({ timeout: 180000 });
  const later = await livelihoodsAt(part, page2, 10);
  checkLive(part, "resumed T10", later, 10);
  await page2.getByRole("button", { name: "Quit" }).click();
  part.check("resumed: the session ends after Quit", (await exited(resumed)) === 0, `exit ${resumed.child.exitCode}`);
  part.check("live: no traceback in the session logs", !/Traceback/.test(first.log + resumed.log));
  if (forkState && existsSync(forkState)) await forkFromState(part, context, origin, forkState);
  part.errorsFree("live");
  await context.close();
}

/**
 * The Fork hint's command (`--fork <state.json> --seed 43 --turns 5`): a
 * state file rebuilds the native pool, so the id-bound records close with
 * the pool-reset reason. The fork's bundle is opened in the viewer.
 */
async function forkFromState(part, context, origin, forkState) {
  const dir = path.join(options.out, "fork-cli");
  mkdirSync(dir, { recursive: true });
  const run = spawnSync(options.python, ["-m", "chronicler.main", "--fork", forkState, "--seed", "43", "--turns", "5",
    "--simulate-only", "--agents", "hybrid", "--output", path.join(dir, "chronicle.md"), "--state", path.join(dir, "state.json")],
  { cwd: dir, env: process.env, encoding: "utf8", timeout: 300000 });
  writeFileSync(path.join(options.out, "fork-cli.log"), `${run.stdout ?? ""}${run.stderr ?? ""}`);
  const file = path.join(dir, "chronicle_bundle.json");
  part.check("fork: `--fork <state.json> --seed 43 --turns 5` completes", run.status === 0 && existsSync(file), (run.stderr ?? "").slice(-300));
  if (!existsSync(file)) return;
  const raw = JSON.parse(readFileSync(file, "utf8"));
  const page = await context.newPage();
  part.watch(page, "fork");
  await page.goto(`${origin}/`, { waitUntil: "load" });
  await page.waitForSelector(".phase75-shell");
  await loadBundle(page, file, raw.world_state.regions.length);
  await openLivelihoods(page);
  const firstTurn = raw.history_delta?.[0]?.turn ?? raw.history?.[0]?.turn;
  const total = raw.metadata.total_turns;
  part.notes.push(`fork bundle: snapshots ${firstTurn}-${total}`);
  let state = await seek(page, total);
  checkDated(part, `fork T${total}`, state, total);
  const reset = (shown) => shown.panels["Remittances and diaspora"]?.notes.find((n) => n.startsWith("The native pool was rebuilt")) ?? null;
  part.check(`fork T${total}: remittances say the native pool was rebuilt`, !!reset(state), JSON.stringify(state.panels["Remittances and diaspora"]?.notes.slice(-2)));
  part.notes.push(`fork remittances note: ${reset(state)}`);
  state = await seek(page, firstTurn);
  checkDated(part, `fork T${firstTurn}`, state, firstTurn);
  const vetText = await page.locator('.systems-shell section[aria-label="Veterans"]').innerText();
  const closed = vetText.split("\n").filter((line) => /pool reset/.test(line));
  part.notes.push(`fork T${firstTurn} veterans closed: ${closed.length} rows naming pool reset`);
  part.check(`fork T${firstTurn}: veteran records close with the pool-reset reason`, closed.length > 0, vetText.slice(0, 200));
  if (firstTurn > 1) {
    state = await seek(page, firstTurn - 1);
    part.check(`fork T${firstTurn - 1} (before the fork's history): no livelihoods observation is said, nothing mounted`,
      PANELS.every((spec) => state.panels[spec.heading] === null)
      && state.bodyNotes.includes(`No livelihoods observation is recorded at snapshot ${firstTurn - 1}.`), JSON.stringify(state.bodyNotes));
    part.check(`fork T${firstTurn - 1}: no NaN or undefined`, !BAD_TEXT.test(state.text));
  }
  await page.close();
}

function firstDifference(a, b) {
  let index = 0;
  while (index < a.length && a[index] === b[index]) index += 1;
  return index === a.length && index === b.length ? "" : `at ${index}: ${JSON.stringify(a.slice(index, index + 80))} vs ${JSON.stringify(b.slice(index, index + 80))}`;
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
  await agents.selectOption("off");
  const remitWhy = await described(box(page, PANELS[3]));
  part.check("Batch Lab: --agents off disables remittances with the runs' mode named", await box(page, PANELS[3]).isDisabled()
    && /requires --agents hybrid \(these runs use --agents off\)/.test(remitWhy), remitWhy);
  await agents.selectOption("");
  const field = (label) => page.locator("label", { hasText: new RegExp(`^${label.replace(/[()]/g, "\\$&")}$`) }).locator("xpath=following-sibling::input");
  await field("Seed Count").fill("3");
  await field("Turns").fill("10");
  await field("Workers (0 = auto)").fill("1");
  await prereq(page, "Workshops", "--workshops").check();
  await box(page, PANELS[3]).check();
  await page.setViewportSize(VIEWPORTS.phone.viewport);
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  part.check("Batch Lab: no horizontal overflow at 390 px with the options open", fits);
  await part.shot(page, "batch-lab-phone.jpg", page.locator("section[aria-label='Experimental features']"));
  await page.setViewportSize(VIEWPORTS.desktop.viewport);
  await page.getByRole("button", { name: /Run Batch/ }).click();
  const cancel = page.getByRole("button", { name: "Cancel Batch" });
  await cancel.waitFor({ timeout: 30000 });
  part.check("Batch Lab: options locked while running", await box(page, PANELS[3]).isDisabled());
  await cancel.click();
  const returned = await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 180000 }).then(() => true, () => false);
  part.check("Batch Lab: Cancel returns to Run Batch", returned);
  part.check("Batch Lab: no error banner after cancel", (await page.locator(".bg-red-900\\/50").count()) === 0,
    await page.locator(".bg-red-900\\/50").allInnerTexts().then((t) => t.join(" | ")));
  part.check("Batch Lab: options enabled again, selection kept", await box(page, PANELS[3]).isEnabled() && await box(page, PANELS[3]).isChecked());
  // run_batch writes output/batch_gui_<time>/batch_<n>/batch_manifest.json under the session's cwd.
  const manifests = [];
  const walk = (dir) => { for (const name of existsSync(dir) ? readdirSync(dir) : []) {
    const entry = path.join(dir, name);
    if (name === "batch_manifest.json") manifests.push(entry);
    else if (statSync(entry).isDirectory() && !name.startsWith("seed_")) walk(entry);
  } };
  walk(path.join(session.dir, "output"));
  const manifest = manifests.length === 1 ? JSON.parse(readFileSync(manifests[0], "utf8")) : null;
  const config = manifest?.simulation ?? {};
  const completed = manifest?.runs?.filter((r) => r.total_turns !== null).length;
  part.notes.push(`batch manifest ${manifests[0] ?? "missing"}: status ${manifest?.status}, ${completed} of ${manifest?.runs?.length} runs `
    + `completed; agents ${config.agents}, workshops ${config.workshops}, remittances ${config.remittances}`);
  part.check("Batch Lab: the batch manifest records the cancellation and the requested switches", manifest?.status === "cancelled"
    && completed < manifest.runs.length && config.workshops === true && config.remittances === true && config.agents === "hybrid",
  `${manifests.length} manifests; ${JSON.stringify({ status: manifest?.status, completed, config: { w: config.workshops, r: config.remittances } })}`);
  await part.shot(page, "batch-lab-after-cancel.jpg");
  // The server is still usable: a second Run Batch is accepted and cancelled the same way.
  await page.getByRole("button", { name: /Run Batch/ }).click();
  await cancel.waitFor({ timeout: 30000 });
  await cancel.click();
  part.check("Batch Lab: a second batch can be started and cancelled",
    await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 180000 }).then(() => true, () => false));
  await page.locator(".phase75-mode-tab", { hasText: /^Setup$/ }).first().click();
  await expandFeatures(page);
  part.check("Batch Lab: the setup form's options are unaffected by the batch", (await box(page, PANELS[3]).count()) === 1
    && !(await box(page, PANELS[3]).isChecked()));
  // The lobby has no Quit control; the session is stopped by its PID below.
  part.notes.push(`Quit buttons in the lobby: ${await page.getByRole("button", { name: "Quit" }).count()}`);
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
