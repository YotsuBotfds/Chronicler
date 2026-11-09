#!/usr/bin/env node
/**
 * Browser QA of the productive-recovery panels on the Livelihoods tab (timber
 * supply, operating wear, recovery crews, maintenance obligation, RS1 rules
 * version 2 and RS2's no_people reason), their feature options and Batch Lab
 * cancellation, on a production build in headless Chromium (Playwright;
 * `require("playwright")`). Opt-in, not CI. Modelled on qa-recovery-skills.mjs.
 *
 *   PYTHONPATH=../src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
 *   node scripts/qa-productive-recovery.mjs [--build dist] --out DIR \
 *     --bundle PR_BUNDLE [--bundle PR_BUNDLE ...] [--control-bundle FILE] \
 *     [--old-bundle FILE] [--python python3] [--parts bundles,old,live,batch]
 *
 * `--bundle` names runs with every productive-recovery switch on in its
 * default mode; `--control-bundle` the same run with every control mode
 * (cost_only, unpaid, reserve_only, no_qualification); `--old-bundle` a run
 * written before the phase (no productive-recovery key, RS1 schema 1).
 * `--python` must import `chronicler` (set PYTHONPATH) and, for the live
 * parts, the native extension. Parts:
 *
 * - bundles: at 1440x900 and 390x844 (touch), each `--bundle` and the
 *   control bundle are opened with "Open saved world file" and the
 *   Livelihoods tab is seeked with the "Historical turn" slider (End,
 *   PageDown, Home, ArrowRight twice, a click on the track, ArrowLeft). At
 *   each stop the six panels (Timber supply, Operating wear, Recovery crews,
 *   Maintenance obligation, Workshop apprenticeship, Repair projects) must be
 *   mounted and readable (none "rejected as malformed"), each heading's
 *   "snapshot N" and every table it labels must name the slider's turn, and
 *   its first note must name simulation turn N - 1. The control bundle must
 *   label every control mode. No "NaN" or "undefined" anywhere in the
 *   systems panel (every tab is read at the last turn); at 390 px no
 *   horizontal page overflow.
 * - old: the old bundle shows apprenticeship (rules version 1) and none of
 *   the four new headings, seeking forward and back. A constructed variant of
 *   the first `--bundle` (made with `--python` and `chronicler.bundle_codec`,
 *   written to `--out`, labelled constructed): turns 1-20 without the four
 *   records, 21-25 with each of the five records malformed, 31-35 with the
 *   turn's frames blanked to null (missing data), 41-43 with no livelihoods
 *   record, 46 with an unknown livelihoods schema. Absent records mount no
 *   panel, malformed ones say "rejected as malformed" with no table, blanked
 *   frames say "unknown, not zero" with no this-turn table, and nothing
 *   crashes, also when rewinding through them.
 * - live: `--live --live-port 0 --simulate-only --agents hybrid --pause-every
 *   5` (cwd `--out/live`). The setup form must list the four switches
 *   unchecked, each disabled with its unmet prerequisites until they are met,
 *   their modes hidden until checked, RS1's rules choice under
 *   apprenticeship, and dropping a prerequisite must drop its dependants. A
 *   20-turn world (template seed 7, 4 civs, 8 regions) runs with every
 *   switch, recovery crews unpaid and the obligation reserve_only. At the
 *   pause at turn 5 the Livelihoods tab is checked through "Inspect world
 *   while paused", rewound to turn 3 and forward again, then Save checkpoint,
 *   Fork and Quit. `--live --resume <checkpoint>` must show the same tab at
 *   turn 5 and date it 10 after Continue. The Fork hint's command
 *   (`--fork <state.json> --seed 9 --turns 5`, a development seed) runs and
 *   its bundle is opened: the panels must read and be dated.
 * - batch: a second live session (cwd `--out/batch`); Batch Lab lists the
 *   four switches unchecked; `--agents off` disables them with the runs' mode
 *   named. A 3-seed (template 12-14, development seeds for viewer QA), 10-turn, 1-worker batch with every switch (timber supply
 *   cost_only, crews unpaid, obligation reserve_only) is started and
 *   cancelled: Run Batch returns with no error banner, the options are kept,
 *   and the batch manifest is cancelled with the switches and modes
 *   recorded. A second batch starts and cancels. No overflow at 390 px.
 *
 * Console errors and page errors fail a part. `--out` is emptied first;
 * `report.json`, screenshots (JPEG), the variant, the sessions' logs and
 * outputs go there. Exits 1 when a check fails.
 */
import { loadPlaywright } from "./lib/playwright.mjs";
import { createServer } from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".json": "application/json", ".wasm": "application/wasm",
};
const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 } },
  phone: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};
/** The panels: heading, feature label and flag, mode select, source-turn note, "unknown" wording, this-turn tables. */
const PANELS = [
  { key: "timber_supply", heading: "Timber supply", label: "Timber supply", flag: "--timber-supply",
    mode: "Timber supply mode --timber-supply-mode", source: /^Simulation turn (\d+)\./, control: /Cost-only control/,
    unknown: /harvest are unknown, not zero/, thisTurn: ["Expeditions this turn at snapshot", "Expedition wages at snapshot"] },
  { key: "operating_wear", heading: "Operating wear", label: "Operating wear", flag: "--operating-wear", mode: null,
    source: /^Simulation turn (\d+)\./, control: null, unknown: /this turn's wear is unknown, not zero/,
    thisTurn: ["Worn sites at snapshot"] },
  { key: "recovery_crews", heading: "Recovery crews", label: "Recovery crews", flag: "--recovery-crews",
    mode: "Recovery crew mode --recovery-crew-mode", source: /^Simulation turn (\d+)\./, control: /Unpaid control/,
    unknown: /crews, wages and sunk coins are unknown, not zero/, thisTurn: ["Granary crew money at snapshot", "Crews at snapshot"] },
  { key: "maintenance_obligation", heading: "Maintenance obligation", label: "Maintenance obligation",
    flag: "--maintenance-obligation", mode: "Maintenance obligation mode --maintenance-obligation-mode",
    source: /^Simulation turn (\d+)\./, control: /Reserve-only control/,
    unknown: /reservations for the next turn are unknown, not zero/,
    thisTurn: ["Reservations decided at snapshot", "Reservations used at snapshot"] },
  { key: "apprenticeship", heading: "Workshop apprenticeship", label: "Apprenticeship", flag: "--apprenticeship",
    mode: "Apprenticeship mode --apprenticeship-mode", source: /^Simulation turn (\d+)\./, control: /No-qualification control/,
    unknown: /continuity this turn is unknown, not zero/, thisTurn: ["Apprenticeship sites at snapshot"] },
  { key: "repair_projects", heading: "Repair projects", label: "Repair projects", flag: "--repair-projects",
    mode: "Repair mode --repair-mode", source: /^Simulation turn (\d+)\./, control: null,
    unknown: /this turn's work, crews and spending are unknown, not zero/, thisTurn: ["Repair accounts at snapshot"] },
];
const NEW = PANELS.slice(0, 4);
const HEADINGS = PANELS.map((p) => p.heading);
const MALFORMED = /rejected as malformed/;
const BAD_TEXT = /\bNaN\b|\bundefined\b/;
/** A development world (template seed 7). */
const WORLD = { seed: "7", turns: "20", civs: "4", regions: "8" };

function parseArgs(argv) {
  const options = { build: path.join(HERE, "..", "dist"), out: null, bundles: [], control: null, old: null,
    python: "python3", parts: "bundles,old,live,batch" };
  for (let index = 0; index < argv.length; index += 2) {
    const [flag, value] = [argv[index], argv[index + 1]];
    if (value === undefined) throw new Error(`${flag} needs a value`);
    if (flag === "--build") options.build = path.resolve(value);
    else if (flag === "--out") options.out = path.resolve(value);
    else if (flag === "--bundle") options.bundles.push(path.resolve(value));
    else if (flag === "--control-bundle") options.control = path.resolve(value);
    else if (flag === "--old-bundle") options.old = path.resolve(value);
    else if (flag === "--python") options.python = value;
    else if (flag === "--parts") options.parts = value;
    else throw new Error(`Unknown option ${flag}`);
  }
  options.parts = new Set(options.parts.split(",").filter(Boolean));
  if (!options.out || ((options.parts.has("bundles") || options.parts.has("old")) && options.bundles.length === 0)) {
    throw new Error("Usage: qa-productive-recovery.mjs --out DIR --bundle FILE [--bundle FILE] [--control-bundle FILE] "
      + "[--old-bundle FILE] [--python PY] [--build DIR] [--parts bundles,old,live,batch]");
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

/** The productive-recovery panels show the record of the slider's turn (natural bundle). */
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


/** Every panel readable (none rejected as malformed) at a turn of a natural bundle. */
function checkReadable(part, tag, state, panels = PANELS) {
  const rejected = panels.filter((spec) => state.panels[spec.heading]?.notes.some((n) => MALFORMED.test(n)));
  part.check(`${tag}: no panel rejected as malformed`, rejected.length === 0,
    rejected.map((spec) => state.panels[spec.heading].notes.find((n) => MALFORMED.test(n))).join(" | "));
}

/** The control bundle names every control mode plainly. */
function checkControls(part, tag, state) {
  for (const spec of PANELS.filter((p) => p.control)) {
    const shown = state.panels[spec.heading];
    part.check(`${tag}: ${spec.heading} labels its control mode`, !!shown?.notes.some((n) => spec.control.test(n)), shown?.notes[0]);
  }
}

// ---------------------------------------------------------------- bundles

async function partBundles(browser, url) {
  const part = partLog("bundles");
  const files = [...options.bundles.map((file) => [file, false]), ...(options.control ? [[options.control, true]] : [])];
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForSelector(".phase75-shell");
    for (const [file, control] of files) {
      const label = path.basename(path.dirname(file));
      const tag = `${viewportName} ${label}`;
      const raw = JSON.parse(readFileSync(file, "utf8"));
      const total = raw.metadata.total_turns;
      await loadBundle(page, file, raw.world_state.regions.length);
      await openLivelihoods(page);
      const slider = page.getByRole("slider", { name: "Historical turn" });
      await slider.focus();
      const at = (state, stop, turn) => {
        checkDated(part, `${tag} ${stop}`, state, turn);
        checkReadable(part, `${tag} ${stop}`, state);
        if (control) checkControls(part, `${tag} ${stop}`, state);
      };

      await slider.press("End");
      await waitPlayhead(page, total);
      let state = await settled(page);
      at(state, "End", total);
      checkFits(part, `${tag} End`, state, viewportName);
      const tab = page.locator('.systems-shell [role="tabpanel"]');
      await part.shot(page, `${viewportName}-${label}-livelihoods-T${total}.jpg`, tab);

      await slider.press("PageDown");
      await waitPlayhead(page, total - 10);
      state = await settled(page);
      at(state, "PageDown", total - 10);
      part.check(`${tag} PageDown: the panels re-dated`, !state.headings.some((h) => h.endsWith(`snapshot ${total}`)), state.headings.join(" | "));

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

// ---------------------------------------------------------------- old bundle, constructed variant (missing data)

const VARIANT_PY = String.raw`
import sys
from chronicler.bundle_codec import load_bundle, dumps_bundle
src, dst = sys.argv[1], sys.argv[2]
b = load_bundle(src)
NEW = ["timber_supply", "operating_wear", "recovery_crews", "maintenance_obligation"]
for s in b["history"]:
    t, l = s["turn"], s.get("livelihoods")
    if not isinstance(l, dict):
        continue
    if t <= 20:                      # before the new records exist
        for k in NEW:
            l.pop(k, None)
    elif 21 <= t <= 25:              # each record malformed
        l["timber_supply"]["source_turn"] = t + 5
        l["operating_wear"]["counters"] = "n/a"
        l["recovery_crews"]["mode"] = "bogus"
        l["maintenance_obligation"]["decisions"] = [{"turn": -1}]
        l["apprenticeship"].pop("rules_version", None)
    elif 31 <= t <= 35:              # this turn's frames blanked to null (missing data)
        ts = l["timber_supply"]
        for k in ("receipts", "ledger", "stores", "needs", "needs_dropped", "deposits"):
            ts[k] = None
        l["operating_wear"]["receipts"] = None
        l["recovery_crews"]["receipts"] = None
        l["recovery_crews"]["ledger"] = None
        l["maintenance_obligation"]["decisions"] = None
        l["maintenance_obligation"]["uses"] = None
        a = l["apprenticeship"]
        a["receipts"], a["continuity"], a["detached"] = None, None, None
        l["repair_projects"]["receipts"] = None
        l["repair_projects"]["ledger"] = None
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
    part.check(`${tag}: before the new records, none of the four new panels is mounted`,
      NEW.every((spec) => state.panels[spec.heading] === null), state.headings.join(" | "));
    part.check(`${tag}: apprenticeship and repair projects still show snapshot ${turn}`,
      state.headings.includes(`Workshop apprenticeship · snapshot ${turn}`) && state.headings.includes(`Repair projects · snapshot ${turn}`),
      state.headings.join(" | "));
  } else if (turn <= 25) {
    for (const [spec, s] of shown.slice(0, 5)) {
      part.check(`${tag}: malformed ${spec.heading} says so, undated, with no table`,
        s !== null && s.heading === spec.heading && s.tables.length === 0 && s.notes.length === 1 && MALFORMED.test(s.notes[0])
        && s.notes[0].includes(`snapshot ${turn}`), JSON.stringify(s));
    }
  } else if (turn >= 31 && turn <= 35) {
    for (const [spec, s] of shown) {
      const thisTurn = s ? s.tables.filter((label) => spec.thisTurn.some((prefix) => label.startsWith(prefix))) : [];
      part.check(`${tag}: blanked ${spec.heading} is dated and says unknown, with no this-turn table`,
        s !== null && s.heading === `${spec.heading} · snapshot ${turn}` && s.notes.some((n) => spec.unknown.test(n)) && thisTurn.length === 0,
        s ? `${s.heading}; ${thisTurn.join(",")}; ${s.notes.find((n) => /unknown/.test(n)) ?? "no unknown note"}` : "not mounted");
    }
    const timber = state.panels["Timber supply"];
    part.check(`${tag}: blanked timber supply claims no zero this-turn line`, timber !== null
      && !timber.notes.some((n) => /^No expedition worked this turn|^All \d+ regions|^No region has open repairs/.test(n)), JSON.stringify(timber?.notes));
    const crews = state.panels["Recovery crews"];
    part.check(`${tag}: blanked recovery crews claim no empty turn`, crews !== null
      && !crews.notes.some((n) => /^No repair crew worked this turn|^This turn:/.test(n)), JSON.stringify(crews?.notes));
  } else if (turn >= 41 && turn <= 43) {
    part.check(`${tag}: no livelihoods record is said, nothing mounted`, shown.every(([, s]) => s === null)
      && state.bodyNotes.includes(`No livelihoods observation is recorded at snapshot ${turn}.`), JSON.stringify(state.bodyNotes));
  } else if (turn === 46) {
    part.check(`${tag}: an unknown livelihoods schema is refused as unreadable`,
      state.bodyNotes.some((n) => n.startsWith(`The livelihoods record at snapshot ${turn} is unreadable`)), JSON.stringify(state.bodyNotes));
  } else {
    checkDated(part, tag, state, turn);
    checkReadable(part, tag, state);
  }
}

async function partOld(browser, url) {
  const part = partLog("old");
  const variant = path.join(options.out, "constructed-missing-data.json");
  buildVariant(options.bundles[0], variant);
  part.notes.push(`constructed variant of ${options.bundles[0]}: ${variant}`);
  const variantTurns = [1, 20, 21, 25, 31, 35, 41, 43, 46, 50, 120];
  for (const viewportName of Object.keys(VIEWPORTS)) {
    const { context, page } = await newPage(browser, viewportName, part);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForSelector(".phase75-shell");
    if (options.old) {
      const tag = `${viewportName} old ${path.basename(path.dirname(options.old))}`;
      const raw = JSON.parse(readFileSync(options.old, "utf8"));
      await loadBundle(page, options.old, raw.world_state.regions.length);
      await openLivelihoods(page);
      const total = raw.metadata.total_turns;
      for (const turn of [total, 1, Math.round(total / 2), total - 1]) {
        const state = await seek(page, turn);
        part.check(`${tag} T${turn}: none of the four new headings`, NEW.every((spec) => state.panels[spec.heading] === null)
          && !state.headings.some((h) => NEW.some((spec) => h.startsWith(spec.heading))), state.headings.join(" | "));
        const rs1 = state.panels["Workshop apprenticeship"];
        part.check(`${tag} T${turn}: apprenticeship rules version 1 is read and dated`,
          rs1?.heading === `Workshop apprenticeship · snapshot ${turn}` && rs1.notes.some((n) => /^RS1 rules version 1/.test(n)), rs1?.notes.slice(0, 2).join(" | "));
        part.check(`${tag} T${turn}: repair projects read and dated`, state.panels["Repair projects"]?.heading === `Repair projects · snapshot ${turn}`);
        checkReadable(part, `${tag} T${turn}`, state, PANELS.slice(4));
        part.check(`${tag} T${turn}: no NaN or undefined`, !BAD_TEXT.test(state.text));
        checkFits(part, `${tag} T${turn}`, state, viewportName);
        if (turn === total) await part.shot(page, `${viewportName}-old-T${turn}.jpg`, page.locator('.systems-shell [role="tabpanel"]'));
      }
    }
    {
      const tag = `${viewportName} constructed`;
      const raw = JSON.parse(readFileSync(variant, "utf8"));
      await loadBundle(page, variant, raw.world_state.regions.length);
      await openLivelihoods(page);
      for (const turn of variantTurns.filter((t) => t <= raw.metadata.total_turns)) {
        const state = await seek(page, turn);
        checkVariant(part, `${tag} T${turn}`, state, turn);
        checkFits(part, `${tag} T${turn}`, state, viewportName);
        if (turn === 21 || turn === 31) await part.shot(page, `${viewportName}-constructed-T${turn}.jpg`, page.locator('.systems-shell [role="tabpanel"]'));
      }
      for (const turn of [35, 22, 12]) {               // rewind through blanked, malformed and absent turns
        const state = await seek(page, turn);
        checkVariant(part, `${tag} rewind T${turn}`, state, turn);
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

/** The four switches are listed, unchecked, their mode selects hidden. */
async function checkDefaults(part, page, tag) {
  for (const panel of NEW) {
    const control = box(page, panel);
    part.check(`${tag}: ${panel.label} offered, unchecked`, (await control.count()) === 1 && !(await control.isChecked()));
    if (panel.mode) {
      part.check(`${tag}: ${panel.label} mode hidden while off`,
        (await page.getByRole("combobox", { name: panel.mode, exact: true }).count()) === 0);
    }
  }
}

const RULES = "Apprenticeship rules --apprenticeship-rules";

async function liveSetup(part, page) {
  const tag = "setup form";
  await expandFeatures(page);
  await checkDefaults(part, page, tag);
  const [timber, wear, crews, obligation] = NEW.map((panel) => box(page, panel));
  const apprentice = box(page, PANELS[4]);
  const repair = box(page, PANELS[5]);
  const workshops = prereq(page, "Workshops", "--workshops");
  const reserves = prereq(page, "Grain reserves", "--grain-reserves");
  const stock = prereq(page, "Timber stock", "--timber-stock");
  const budgets = prereq(page, "Local budgets", "--local-budgets");
  const why = [await described(wear), await described(timber), await described(crews), await described(obligation)];
  part.notes.push(`setup reasons with nothing selected: ${why.join(" / ")}`);
  part.check(`${tag}: the four switches are disabled with nothing selected`,
    await wear.isDisabled() && await timber.isDisabled() && await crews.isDisabled() && await obligation.isDisabled());
  part.check(`${tag}: each disabled switch names its unmet prerequisites`, /Unavailable: requires --workshops\./.test(why[0])
    && /Unavailable: requires --repair-projects; requires --timber-stock\./.test(why[1])
    && /Unavailable: requires --repair-projects\./.test(why[2])
    && /Unavailable: requires --local-budgets; requires --repair-projects\./.test(why[3]), why.join(" / "));

  await workshops.check();
  part.check(`${tag}: workshops enables operating wear`, await wear.isEnabled());
  await apprentice.check();
  const rules = page.getByRole("combobox", { name: RULES, exact: true });
  part.check(`${tag}: RS1 rules choice shown under apprenticeship, version 2 by default`, (await rules.count()) === 1
    && (await rules.inputValue()) === "2" && (await rules.locator("option").allTextContents()).join("|") === "2 (default)|1",
  await rules.locator("option").allTextContents().then((t) => t.join("|"), () => "missing"));
  await repair.check();
  part.check(`${tag}: repair projects enable recovery crews, not timber supply or the obligation`,
    await crews.isEnabled() && await timber.isDisabled() && await obligation.isDisabled());
  await stock.check();
  part.check(`${tag}: timber stock enables timber supply`, await timber.isEnabled());
  await reserves.check();
  await budgets.check();
  part.check(`${tag}: local budgets enable the maintenance obligation`, await obligation.isEnabled());
  for (const control of [timber, crews, obligation]) await control.check();
  await repair.uncheck();
  part.check(`${tag}: dropping repair projects drops timber supply, crews and the obligation`,
    !(await timber.isChecked()) && !(await crews.isChecked()) && !(await obligation.isChecked())
    && (await page.getByRole("combobox", { name: NEW[0].mode, exact: true }).count()) === 0);

  // The world's selection: every switch, recovery crews unpaid and the obligation reserve_only.
  await repair.check();
  for (const control of [timber, wear, crews, obligation]) await control.check();
  for (const panel of NEW.filter((p) => p.mode)) {
    part.check(`${tag}: ${panel.label} mode select shown when checked`, (await page.getByRole("combobox", { name: panel.mode, exact: true }).count()) === 1);
  }
  await page.getByRole("combobox", { name: NEW[2].mode, exact: true }).selectOption("unpaid");
  await page.getByRole("combobox", { name: NEW[3].mode, exact: true }).selectOption("reserve_only");
  const summary = await page.locator("section[aria-label='Experimental features'] [aria-live=polite]").innerText();
  part.notes.push(`setup summary: ${summary}`);
  part.check(`${tag}: summary lists the selected flags`, ["--workshops", "--apprenticeship", "--repair-projects", "--timber-stock",
    "--timber-supply", "--operating-wear", "--recovery-crews", "--recovery-crew-mode=unpaid", "--grain-reserves", "--local-budgets",
    "--maintenance-obligation", "--maintenance-obligation-mode=reserve_only"].every((flag) => summary.includes(flag))
    && !summary.includes("--timber-supply-mode") && !summary.includes("--apprenticeship-rules"), summary);
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

function checkLive(part, tag, state, turn) {
  checkDated(part, tag, state, turn);
  checkReadable(part, tag, state);
  const crews = state.panels["Recovery crews"];
  part.check(`${tag}: recovery crews run the requested unpaid control`, !!crews?.notes.some((n) => /Unpaid control/.test(n)), crews?.notes[0]);
  const obligation = state.panels["Maintenance obligation"];
  part.check(`${tag}: the obligation runs the requested reserve_only control`,
    !!obligation?.notes.some((n) => /Reserve-only control/.test(n)), obligation?.notes[0]);
  const timber = state.panels["Timber supply"];
  part.check(`${tag}: timber supply runs its default supply mode`, !!timber?.notes.some((n) => /\. Supply:/.test(n)), timber?.notes[0]);
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
  const later = await livelihoodsAt(part, page2, 10);
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
  for (const turn of [total, firstTurn]) {
    const state = await seek(page, turn);
    checkDated(part, `fork T${turn}`, state, turn);
    checkReadable(part, `fork T${turn}`, state);
    part.check(`fork T${turn}: no NaN or undefined`, !BAD_TEXT.test(state.text));
    const rs1 = state.panels["Workshop apprenticeship"]?.notes.find((n) => /pool reset/.test(n));
    part.notes.push(`fork T${turn} apprenticeship pool-reset note: ${rs1 ?? "none"}`);
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
  const [timber, wear, crews, obligation] = NEW.map((panel) => box(page, panel));
  const workshops = prereq(page, "Workshops", "--workshops");
  await workshops.check();
  await agents.selectOption("off");
  const wearWhy = await described(wear);
  part.check("Batch Lab: --agents off drops workshops and disables operating wear with the runs' mode named",
    !(await workshops.isChecked()) && await wear.isDisabled() && /requires --agents hybrid \(these runs use --agents off\)/.test(wearWhy), wearWhy);
  await agents.selectOption("");
  const field = (label) => page.locator("label", { hasText: new RegExp(`^${label.replace(/[()]/g, "\\$&")}$`) }).locator("xpath=following-sibling::input");
  // Template seeds 12-14: development seeds declared for viewer QA (never a cohort or pilot seed).
  await field("Start Seed").fill("12");
  await field("Seed Count").fill("3");
  await field("Turns").fill("10");
  await field("Workers (0 = auto)").fill("1");
  for (const [label, flag] of [["Grain reserves", "--grain-reserves"], ["Workshops", "--workshops"], ["Repair projects", "--repair-projects"],
    ["Timber stock", "--timber-stock"], ["Local budgets", "--local-budgets"]]) await prereq(page, label, flag).check();
  for (const control of [timber, wear, crews, obligation]) await control.check();
  await page.getByRole("combobox", { name: NEW[0].mode, exact: true }).selectOption("cost_only");
  await page.getByRole("combobox", { name: NEW[2].mode, exact: true }).selectOption("unpaid");
  await page.getByRole("combobox", { name: NEW[3].mode, exact: true }).selectOption("reserve_only");
  await page.setViewportSize(VIEWPORTS.phone.viewport);
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  part.check("Batch Lab: no horizontal overflow at 390 px with the options open", fits);
  await part.shot(page, "batch-lab-phone.jpg", page.locator("section[aria-label='Experimental features']"));
  await page.setViewportSize(VIEWPORTS.desktop.viewport);
  await page.getByRole("button", { name: /Run Batch/ }).click();
  const cancel = page.getByRole("button", { name: "Cancel Batch" });
  await cancel.waitFor({ timeout: 30000 });
  part.check("Batch Lab: options locked while running", await timber.isDisabled() && await obligation.isDisabled());
  await cancel.click();
  const returned = await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 300000 }).then(() => true, () => false);
  part.check("Batch Lab: Cancel returns to Run Batch", returned);
  part.check("Batch Lab: no error banner after cancel", (await page.locator(".bg-red-900\\/50").count()) === 0,
    await page.locator(".bg-red-900\\/50").allInnerTexts().then((t) => t.join(" | ")));
  part.check("Batch Lab: options enabled again, selection kept", await timber.isEnabled() && await timber.isChecked()
    && await obligation.isChecked() && await crews.isChecked() && await wear.isChecked());
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
  const recorded = { timber_supply: config.timber_supply, timber_supply_mode: config.timber_supply_mode,
    operating_wear: config.operating_wear, recovery_crews: config.recovery_crews, recovery_crew_mode: config.recovery_crew_mode,
    maintenance_obligation: config.maintenance_obligation, maintenance_obligation_mode: config.maintenance_obligation_mode,
    repair_projects: config.repair_projects, timber_stock: config.timber_stock, local_budgets: config.local_budgets };
  part.notes.push(`batch manifest ${manifests[0] ?? "missing"}: status ${manifest?.status}, ${completed} of ${manifest?.runs?.length} runs `
    + `completed; agents ${config.agents}; ${JSON.stringify(recorded)}`);
  part.check("Batch Lab: the batch manifest records the cancellation and the requested switches and modes", manifest?.status === "cancelled"
    && completed < manifest.runs.length && config.agents === "hybrid" && JSON.stringify(recorded) === JSON.stringify({
    timber_supply: true, timber_supply_mode: "cost_only", operating_wear: true, recovery_crews: true, recovery_crew_mode: "unpaid",
    maintenance_obligation: true, maintenance_obligation_mode: "reserve_only", repair_projects: true, timber_stock: true, local_budgets: true }),
  `${manifests.length} manifests; ${manifest?.status}; ${JSON.stringify(recorded)}`);
  await part.shot(page, "batch-lab-after-cancel.jpg");
  await page.getByRole("button", { name: /Run Batch/ }).click();
  await cancel.waitFor({ timeout: 30000 });
  await cancel.click();
  part.check("Batch Lab: a second batch can be started and cancelled",
    await page.getByRole("button", { name: /Run Batch/ }).waitFor({ timeout: 300000 }).then(() => true, () => false));
  await page.locator(".phase75-mode-tab", { hasText: /^Setup$/ }).first().click();
  await expandFeatures(page);
  part.check("Batch Lab: the setup form's options are unaffected by the batch", (await box(page, NEW[0]).count()) === 1
    && !(await box(page, NEW[0]).isChecked()));
  part.check("batch: no traceback in the session log", !/Traceback/.test(session.log), session.log.match(/Traceback[\s\S]{0,400}/)?.[0]);
  part.errorsFree("batch");
  await context.close();
}

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


function firstDifference(a, b) {
  let index = 0;
  while (index < a.length && a[index] === b[index]) index += 1;
  return index === a.length && index === b.length ? "" : `at ${index}: ${JSON.stringify(a.slice(index, index + 80))} vs ${JSON.stringify(b.slice(index, index + 80))}`;
}

async function main() {
  rmSync(options.out, { recursive: true, force: true });
  mkdirSync(options.out, { recursive: true });
  const { chromium } = loadPlaywright();
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
