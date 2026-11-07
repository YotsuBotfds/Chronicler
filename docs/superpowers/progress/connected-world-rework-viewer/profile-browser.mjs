#!/usr/bin/env node
/** Paired actual production UI timings; no simulations, record edits or narration. */
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { readFileSync, readdirSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { performance } from "node:perf_hooks";
const require = createRequire(import.meta.url), { chromium } = require("playwright");
const options = { config: null, out: null, python: "python", "cpu-profile": "false" };
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, "");
  if (!(key in options) || !process.argv[i + 1]) throw new Error(`Invalid option ${process.argv[i]}`);
  options[key] = process.argv[i + 1];
}
if (!options.config || !options.out) throw new Error("Required --config FILE --out DIRECTORY [--python PYTHON] [--cpu-profile true]");
options.out = path.resolve(options.out); mkdirSync(options.out, { recursive: true });
const config = JSON.parse(readFileSync(options.config, "utf8"));
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const assets = (root, prefix = "") => Object.fromEntries(readdirSync(root, { withFileTypes: true }).sort((a,b) => a.name.localeCompare(b.name)).flatMap(e => {
  const relative = prefix + e.name, file = path.join(root, e.name);
  return e.isDirectory() ? Object.entries(assets(file, relative + "/")) : [[relative, sha(readFileSync(file))]];
}));
const report = { config, generated_at: new Date().toISOString(), script_sha256: sha(readFileSync(new URL(import.meta.url))),
  measurements: [], builds: {}, elapsed_seconds: null, note: "New browser context per cold sample; same-page tab reopen is warm. Desktop/phone are Chromium viewports on the same host, without CPU throttling. Load includes decode worker and map readiness; renderer CPU metrics exclude worker CPU. OS file caches may be warm. All observations retained." };
const servers = {}, started = performance.now();
for (const [variant, directory] of Object.entries(config.builds)) {
  const root = path.resolve(directory); report.builds[variant] = { directory: root, assets: assets(root) };
  const server = createServer((request, response) => { try {
    let file = path.resolve(root, "." + decodeURIComponent(new URL(request.url, "http://x").pathname));
    if (!file.startsWith(root + path.sep) && file !== root) { response.writeHead(403).end(); return; }
    if (statSync(file).isDirectory()) file = path.join(file, "index.html");
    response.writeHead(200, { "content-type": ({".js":"text/javascript",".css":"text/css",".html":"text/html",".svg":"image/svg+xml"})[path.extname(file)] ?? "application/octet-stream" });
    response.end(readFileSync(file));
  } catch { response.writeHead(404).end(); } });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  servers[variant] = { server, url: `http://127.0.0.1:${server.address().port}` };
}
const browser = await chromium.launch(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {});
const metricMap = async cdp => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(m => [m.name, m.value]));
const metricDelta = (a, b) => Object.fromEntries(["TaskDuration","ScriptDuration","LayoutDuration","RecalcStyleDuration"].map(k => [k, (b[k] - a[k]) * 1000]));
try {
  for (let caseIndex = 0; caseIndex < config.cases.length; caseIndex++) {
    const fixture = config.cases[caseIndex], raw = readFileSync(fixture.bundle);
    if (sha(raw) !== fixture.sha256) throw new Error(`Input hash mismatch: ${fixture.name}`);
    const decoded = spawnSync(options.python, ["-c", "import json,sys;from chronicler.bundle_codec import load_bundle;b=load_bundle(sys.argv[1]);print(json.dumps({'regions':len(b['world_state']['regions']),'snapshots':len(b['history']),'turns':[s['turn'] for s in b['history']]}))", fixture.bundle], { encoding: "utf8" });
    if (decoded.status !== 0) throw new Error(decoded.stderr);
    const expected = JSON.parse(decoded.stdout);
    for (let repeat = 0; repeat < config.repeats; repeat++) {
      const variants = (caseIndex + repeat) % 2 ? ["after", "before"] : ["before", "after"];
      for (const variant of variants) for (const [viewport, settings] of Object.entries({ desktop: { viewport:{width:1440,height:900} }, phone:{viewport:{width:390,height:844},isMobile:true,hasTouch:true} })) {
        if ((performance.now() - started) / 1000 > config.elapsed_ceiling_seconds) throw new Error("Declared elapsed ceiling exhausted; preserve partial report");
        const row = { case: fixture.name, variant, viewport, repeat, input_sha256: fixture.sha256, input_bytes: raw.length,
          expected, timings_ms: {}, renderer_cpu_ms: {}, heap_used_bytes: {}, initial_turn: null, selected_entity: null, option_count: null, displayed_rows: null, messages: [] };
        const context = await browser.newContext({ ...settings, locale: "en-US", deviceScaleFactor: 1 }), page = await context.newPage();
        page.on("pageerror", e => row.messages.push(`pageerror: ${e.message}`));
        page.on("console", m => { if (m.type() === "error") row.messages.push(`console: ${m.text()}`); });
        const cdp = await context.newCDPSession(page); await cdp.send("Performance.enable");
        try {
          await page.goto(servers[variant].url);
          let metrics = await metricMap(cdp), at = performance.now();
          await page.getByLabel("Open saved world file").setInputFiles(fixture.bundle);
          await page.waitForFunction(n => document.querySelectorAll(".phase75-region-node").length === n && !!document.querySelector(".phase75-playhead-label") && !document.querySelector(".saved-world-loading"), expected.regions, {timeout:120000});
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          row.timings_ms.load = performance.now() - at;
          let next = await metricMap(cdp); row.renderer_cpu_ms.load = metricDelta(metrics, next); row.heap_used_bytes.loaded = next.JSHeapUsedSize;
          row.initial_turn = await page.locator(".phase75-playhead-label").innerText();
          const profile = options["cpu-profile"] === "true" && repeat === 0 && viewport === "desktop";
          if (profile) { await cdp.send("Profiler.enable"); await cdp.send("Profiler.start"); }
          metrics = await metricMap(cdp); at = performance.now();
          await page.getByRole("tab", { name:"Livelihoods",exact:true }).click();
          await page.getByRole("region", { name:"Linked histories",exact:true }).waitFor();
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          row.timings_ms.cold_panel = performance.now() - at;
          next = await metricMap(cdp); row.renderer_cpu_ms.cold_panel = metricDelta(metrics, next); row.heap_used_bytes.cold_panel = next.JSHeapUsedSize;
          if (profile) { const data = await cdp.send("Profiler.stop"); writeFileSync(path.join(options.out, `${fixture.name}-${variant}.cpuprofile`), JSON.stringify(data.profile)); }
          await page.getByRole("tab", { name:"Epidemics",exact:true }).click();
          await page.getByRole("tabpanel", { name:"Epidemics",exact:true }).waitFor();
          metrics = await metricMap(cdp); at = performance.now();
          await page.getByRole("tab", { name:"Livelihoods",exact:true }).click();
          await page.getByRole("region", { name:"Linked histories",exact:true }).waitFor();
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          row.timings_ms.warm_reopen = performance.now() - at;
          next = await metricMap(cdp); row.renderer_cpu_ms.warm_reopen = metricDelta(metrics, next); row.heap_used_bytes.warm_reopen = next.JSHeapUsedSize;
          const slider = page.getByRole("slider", { name:"Historical turn" }); at = performance.now();
          await slider.focus(); await slider.press("End");
          await page.waitForFunction(n => document.querySelector(".phase75-playhead-label")?.textContent === `T${n}`, expected.turns.at(-1));
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          row.timings_ms.latest_turn = performance.now() - at;
          const selector = page.getByRole("region", {name:"Linked histories",exact:true}).getByLabel("Recorded entity");
          const ids = await selector.locator("option").evaluateAll(os => os.map(o => o.value));
          row.option_count = ids.length;
          const entity = ids.includes("person:13") ? "person:13" : ids.find(id => id.startsWith("person:")) ?? ids[0];
          at = performance.now(); await selector.selectOption(entity);
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          row.timings_ms.select_entity = performance.now() - at; row.selected_entity = entity;
          row.displayed_rows = await page.getByRole("region", {name:"Linked histories",exact:true}).locator("tbody tr").count();
          if (row.messages.length) throw new Error(row.messages.join("\n"));
          report.measurements.push(row); writeFileSync(path.join(options.out,"report.json"), JSON.stringify(report,null,2)+"\n");
          console.log(JSON.stringify({case:row.case,variant,viewport,repeat,timings_ms:row.timings_ms}));
        } finally { await context.close(); }
      }
    }
    if (sha(readFileSync(fixture.bundle)) !== fixture.sha256) throw new Error("Source bundle changed during profile");
  }
  for (const [variant, directory] of Object.entries(config.builds)) if (JSON.stringify(assets(path.resolve(directory))) !== JSON.stringify(report.builds[variant].assets)) throw new Error("Build changed during profile");
} finally {
  report.elapsed_seconds = (performance.now() - started) / 1000;
  writeFileSync(path.join(options.out,"report.json"), JSON.stringify(report,null,2)+"\n");
  await browser.close(); for (const {server} of Object.values(servers)) await new Promise(resolve => server.close(resolve));
}
