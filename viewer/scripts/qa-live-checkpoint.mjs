#!/usr/bin/env node
/**
 * Browser QA of the live "Save checkpoint" control and `--live --resume`
 * (docs/integration/checkpoint-continuation.md, section 11). Opt-in, not CI.
 *
 *   PYTHONPATH=../src node scripts/qa-live-checkpoint.mjs \
 *     [--python python3] [--viewer http://localhost:5173] [--out DIR] [--agents off]
 *
 * Needs a running viewer (`npm run dev`, or `npm run build` and
 * `npm run preview -- --port 4173`), headless Chromium through Playwright
 * (`require("playwright")`) and a Python that imports `chronicler`. It
 * starts its own live sessions (`--live --live-port 0 --simulate-only`,
 * stopped by their own PIDs) and, in headless Chromium:
 *
 * 1. opens the link the first session prints, launches a 20-turn world
 *    (seed 42, 4 civs, 8 regions) from the setup form, waits for the pause
 *    at turn 5 and notes what the viewer shows (turn, chronicle rail,
 *    civilization metrics);
 * 2. clicks Save checkpoint: the panel must show "Checkpoint saved at turn
 *    5" with the server's path (`<out>/session/live_checkpoints/turn_0005.ckpt`,
 *    on disk) and the hint `--live --resume <path>`; then Quit;
 * 3. starts `--live --resume <path>` and opens its link: the viewer must
 *    start paused at turn 5 with the same history as at step 1, Continue
 *    must run on to the pause at turn 10, then Quit;
 * 4. meanwhile opens the resumed session with the first session's (stale)
 *    token and with no token: the viewer must show its refusal message and
 *    no history, and the session must go on as before.
 *
 * Screenshots, the sessions' outputs and logs and `report.json` go to
 * `--out` (default: `chronicler-live-checkpoint-qa` in the temporary
 * directory). Exits 1 when a check fails.
 */
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, rmSync, createWriteStream, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const DEFAULT_ORIGINS = new Set(["http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173",
  "http://localhost:4173", "http://127.0.0.1:4173", "http://[::1]:4173"]);
const REFUSED = "Could not connect to the live server";
const WORLD = { seed: "42", turns: "20", civs: "4", regions: "8" };

function parseArgs(argv) {
  // The default output path has no hyphen or space: the panel must wrap a
  // path that has none.
  const options = { python: "python3", viewer: "http://localhost:5173",
    out: path.join(os.tmpdir(), "chronicler_live_checkpoint_qa"), agents: "off" };
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index].replace(/^--/, "");
    if (!(key in options) || argv[index + 1] === undefined) throw new Error(`unknown or empty option ${argv[index]}`);
    options[key] = argv[index + 1];
  }
  const viewer = new URL(options.viewer);
  if (!LOCAL_HOSTS.has(viewer.hostname)) throw new Error("browser QA is restricted to a local viewer");
  options.viewer = viewer.origin;
  options.out = path.resolve(options.out);
  return options;
}

const options = parseArgs(process.argv.slice(2));
const sessions = [];
const checks = [];
const shots = [];

function check(name, ok, detail = "") {
  checks.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${detail ? `: ${detail}` : ""}`);
}

/** A live session; resolves with its printed viewer link once it is listening. */
function liveSession(label, args) {
  const dir = path.join(options.out, label);
  mkdirSync(dir, { recursive: true });
  const extra = DEFAULT_ORIGINS.has(options.viewer) ? [] : ["--live-origin", options.viewer];
  const child = spawn(options.python, ["-u", "-m", "chronicler.main", "--live", "--live-port", "0",
    "--simulate-only", "--agents", options.agents, ...extra, ...args,
    "--output", path.join(dir, "chronicle.md"), "--state", path.join(dir, "state.json")],
  { cwd: options.out, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
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
        const printed = new URL(match[1]);
        session.link = `${options.viewer}/${printed.search}`;
        session.ws = printed.searchParams.get("ws");
        session.token = printed.searchParams.get("token");
        clearTimeout(timer);
        resolve(session);
      }
    };
    child.stdout.on("data", read);
    child.stderr.on("data", read);
    child.on("exit", (code) => {
      session.exit = code;
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

async function shot(page, name) {
  const file = path.join(options.out, `${name}.png`);
  await page.screenshot({ path: file });
  shots.push(file);
}

/** What the viewer shows of the run's history while paused. */
async function shownHistory(page) {
  const text = await page.locator("body").innerText();
  const turn = text.match(/TURN\s+(\d+ \/ \d+)/)?.[1] ?? null;
  const chronicle = [...text.matchAll(/CHRONICLE\s+Turn (\d+)/g)].map((m) => Number(m[1]));
  const metrics = [...text.matchAll(/^(.+?)Econ (\d+) · Mil (\d+) · Era (\w+)$/gm)].map((m) => m[0]);
  return { turn, chronicle, metrics };
}

/** Every line box of each element ends inside the container's box. */
async function fits(container, elements) {
  const outer = await container.boundingBox();
  for (const element of elements) {
    const right = await element.evaluate((node) =>
      Math.max(...[...node.getClientRects()].map((rect) => rect.right)));
    if (!outer || right > outer.x + outer.width + 1) return false;
  }
  return true;
}

async function pausedAt(page, turn) {
  await page.getByRole("heading", { name: `Paused at Turn ${turn}` }).waitFor({ timeout: 120000 });
}

async function main() {
  rmSync(options.out, { recursive: true, force: true });
  mkdirSync(options.out, { recursive: true });
  const browser = await chromium.launch();
  const errors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(String(error)));

    // 1. A new session: launch from the setup form, pause at turn 5.
    const first = await liveSession("session", ["--pause-every", "5"]);
    await page.goto(first.link);
    await page.getByRole("button", { name: "Run World" }).waitFor({ timeout: 60000 });
    await page.getByLabel("Seed").fill(WORLD.seed);
    await page.getByLabel("Turns").fill(WORLD.turns);
    await page.getByLabel("Civilizations").fill(WORLD.civs);
    await page.getByLabel("Regions").fill(WORLD.regions);
    await shot(page, "01-setup");
    await page.getByRole("button", { name: "Run World" }).click();
    await pausedAt(page, 5);
    const before = await shownHistory(page);
    check("first session pauses at turn 5", before.turn === "5 / 20", JSON.stringify(before.turn));
    await shot(page, "02-paused-turn-5");

    // 2. Save checkpoint.
    await page.getByRole("button", { name: "Save checkpoint" }).click();
    const saved = page.getByRole("status").filter({ hasText: "Checkpoint saved at turn 5" });
    await saved.waitFor({ timeout: 60000 });
    const expected = path.join(first.dir, "live_checkpoints", "turn_0005.ckpt");
    const shownPath = await saved.locator("code").innerText();
    check("the saved path is the server's", shownPath === expected, shownPath);
    check("the checkpoint file exists", existsSync(expected));
    const hint = saved.getByText(`--live --resume ${expected}`, { exact: true });
    check("the resume hint is shown", await hint.isVisible());
    check("the saved path and the hint fit the panel", await fits(saved, [saved.locator("code"), hint]));
    await shot(page, "03-checkpoint-saved");
    // The fork control shows a path in the same panel.
    await page.getByRole("button", { name: "Fork" }).click();
    const forked = page.getByText("Fork saved to:").locator("..");
    await forked.waitFor({ timeout: 60000 });
    const forkHint = forked.getByText(/--fork .*state\.json --seed SEED --turns TURNS/);
    check("the fork hint names --fork", await forkHint.isVisible());
    check("the fork path and its hint fit the panel", await fits(forked, [forked.locator("code"), forkHint]));
    await shot(page, "03b-forked");
    await page.getByRole("button", { name: "Quit" }).click();
    check("the first session ends after Quit", (await exited(first)) === 0, `exit ${first.child.exitCode}`);
    await page.close();

    // 3. --live --resume: paused at turn 5 with the same history.
    const resumed = await liveSession("resumed", ["--resume", expected]);
    const page2 = await context.newPage();
    page2.on("pageerror", (error) => errors.push(String(error)));
    await page2.goto(resumed.link);
    await pausedAt(page2, 5);
    const after = await shownHistory(page2);
    check("the resumed session starts paused at turn 5", after.turn === "5 / 20", JSON.stringify(after.turn));
    check("the resumed viewer shows the earlier chronicle",
      JSON.stringify(after.chronicle) === JSON.stringify([1, 2, 3, 4, 5]) &&
      JSON.stringify(after.chronicle) === JSON.stringify(before.chronicle), JSON.stringify(after.chronicle));
    check("the resumed viewer shows the same civilization metrics",
      after.metrics.length > 0 && JSON.stringify(after.metrics) === JSON.stringify(before.metrics),
      JSON.stringify(after.metrics));
    await shot(page2, "04-resumed-paused-turn-5");

    // 4. Refusals while the resumed session runs: a stale token, no token.
    const refusals = [["stale-token", `${options.viewer}/?ws=${resumed.ws}&token=${first.token}`],
      ["no-token", `${options.viewer}/?ws=${resumed.ws}`]];
    for (const [name, url] of refusals) {
      const refused = await context.newPage();
      await refused.goto(url);
      const message = refused.getByText(REFUSED);
      await message.first().waitFor({ timeout: 30000 }).catch(() => {});
      check(`a viewer with ${name.replace("-", " ")} is refused`, await message.first().isVisible());
      check(`the ${name} viewer gets no history`, !(await refused.getByRole("heading", { name: /Paused at Turn/ }).count()));
      await message.first().scrollIntoViewIfNeeded().catch(() => {});
      await shot(refused, `05-refused-${name}`);
      await refused.close();
    }
    check("the refusals left no error in the session's log", !/Traceback|Error/.test(resumed.log));

    // The resumed session runs on from turn 5.
    await page2.bringToFront();
    await page2.getByRole("button", { name: "Continue" }).click();
    await pausedAt(page2, 10);
    const later = await shownHistory(page2);
    check("Continue runs the resumed session to the pause at turn 10", later.turn === "10 / 20",
      JSON.stringify(later.turn));
    check("the turns after the resume extend the history",
      JSON.stringify(later.chronicle) === JSON.stringify([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
      JSON.stringify(later.chronicle));
    await shot(page2, "06-resumed-paused-turn-10");
    await page2.getByRole("button", { name: "Quit" }).click();
    check("the resumed session ends after Quit", (await exited(resumed)) === 0, `exit ${resumed.child.exitCode}`);
    check("no page errors", errors.length === 0, errors.join(" | "));
  } finally {
    await browser.close();
    for (const session of sessions) {
      if (session.child.exitCode === null) {
        session.child.kill();  // this session's own process
        await exited(session, 10000);
      }
    }
  }
}

main()
  .catch((error) => {
    check("the QA run completed", false, String(error?.stack ?? error));
  })
  .finally(() => {
    const failed = checks.filter((c) => !c.ok).length;
    writeFileSync(path.join(options.out, "report.json"), `${JSON.stringify({
      viewer: options.viewer, python: options.python, agents: options.agents, world: WORLD, checks,
      screenshots: shots, sessions: sessions.map((s) => ({ label: s.label, pid: s.child.pid, exit: s.child.exitCode })),
    }, null, 2)}\n`);
    console.log(`${checks.length - failed} of ${checks.length} checks passed; report in ${options.out}`);
    process.exitCode = failed ? 1 : 0;
  });
