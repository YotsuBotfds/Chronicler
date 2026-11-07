#!/usr/bin/env node
/** Production Chromium saved-bundle journeys. No simulation, held seeds or paid calls.
 * NODE_PATH=/path/to/playwright/node_modules PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers 
 * PYTHONPATH=src node viewer/scripts/qa-connected-world.mjs --build viewer/dist 
 *   --bundle chronicle_bundle.json --out /tmp/qa --python python --journey relief|leagues|branches|history
 * Uses actual file upload, keyboard timeline seek, desktop and phone/touch viewports.
 * Bundle expectations are decoded independently by the Python bundle codec.
 */
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const options = { build: "viewer/dist", python: "python", journey: "history", out: null, bundle: null, turns: null };
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, "");
  if (!(key in options) || !process.argv[i + 1]) throw new Error(`Unknown/missing option ${process.argv[i]}`);
  options[key] = process.argv[i + 1];
}
if (!options.out || !options.bundle || !["relief", "leagues", "branches", "history"].includes(options.journey)) throw new Error("Required: --bundle FILE --out DIR --journey relief|leagues|branches|history");
for (const key of ["build", "bundle", "out"]) options[key] = path.resolve(options[key]);
mkdirSync(options.out, { recursive: true });
const py = spawnSync(options.python, ["-c", `
import json,sys
from chronicler.bundle_codec import load_bundle
b=load_bundle(sys.argv[1]); turns=set(map(int,sys.argv[2].split(','))) if sys.argv[2] else None
print(json.dumps({'constructed':(b.get('metadata') or {}).get('constructed'),'regions':[r['name'] for r in b['world_state']['regions']],
 'history':[{'turn':s['turn'],'livelihoods':s.get('livelihoods')} if turns is None or s['turn'] in turns else None for s in b['history']]}))
`, options.bundle, options.turns ?? (options.journey === "relief" ? "86,87" : options.journey === "leagues" ? "120" : "")], { encoding: "utf8", maxBuffer: 128 * 1024 * 1024 });
if (py.status !== 0) throw new Error(py.stderr || "Python independent bundle decoder failed");
const expected = JSON.parse(py.stdout);
let snapshots = expected.history.filter(Boolean);
if (options.journey === "branches" && !options.turns) {
  const funded = snapshots.filter((s)=>s.livelihoods?.movement_branches?.frame?.rows?.some((r)=>r.status === "funded"));
  if (!funded.length) throw new Error("Natural branch journey requires an actual funded receipt");
  snapshots = funded.length > 1 ? [funded[0],funded.at(-1)] : funded;
}
const buildAssets = (directory, prefix="") => Object.fromEntries(readdirSync(directory,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name)).flatMap((entry)=>{
  const relative=prefix+entry.name, full=path.join(directory,entry.name);
  return entry.isDirectory()?Object.entries(buildAssets(full,relative+"/")):[[relative,createHash("sha256").update(readFileSync(full)).digest("hex")]];
}));
const report = { generated: new Date().toISOString(), ...options, constructed: expected.constructed, build_files_sha256:buildAssets(options.build),
  bundle_sha256: createHash("sha256").update(readFileSync(options.bundle)).digest("hex"),
  build_index_sha256: createHash("sha256").update(readFileSync(path.join(options.build,"index.html"))).digest("hex"),
  evidence: "Provided saved bundle; construction metadata retained explicitly; expectations decoded by Python bundle_codec. Browser journeys are bounded UI checks, not qualification.", viewports: {} };
let failures = 0;
const check = (result, label, ok, detail = "") => { result.checks.push({ label, ok: !!ok, detail }); if (!ok) failures++; console.log(`${ok ? "ok" : "FAIL"} ${label}${ok ? "" : `: ${detail}`}`); };
const fmt = (n) => n.toLocaleString("en-US", { maximumFractionDigits: 3 });
const units = (n) => fmt(n / 1000);
const server = createServer((request,response) => {
  try {
    let file = path.resolve(options.build, "." + decodeURIComponent(new URL(request.url,"http://x").pathname));
    if (!file.startsWith(options.build + path.sep) && file !== options.build) { response.writeHead(403).end(); return; }
    if (statSync(file).isDirectory()) file = path.join(file,"index.html");
    const types = {".html":"text/html", ".js":"text/javascript", ".css":"text/css", ".svg":"image/svg+xml", ".json":"application/json"};
    response.writeHead(200,{"content-type": types[path.extname(file)] ?? "application/octet-stream"}); response.end(readFileSync(file));
  } catch { response.writeHead(404).end(); }
});
await new Promise((resolve) => server.listen(0,"127.0.0.1",resolve));
const { chromium } = require("playwright");
const browser = await chromium.launch(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {});
const url = `http://127.0.0.1:${server.address().port}`;
async function seek(page, turn) {
  const slider = page.getByRole("slider", { name: "Historical turn" });
  await slider.focus(); await slider.press("Home");
  for (let n=0; n<Math.floor((turn-1)/10); n++) await slider.press("PageUp");
  for (let n=0; n<(turn-1)%10; n++) await slider.press("ArrowRight");
  await page.waitForFunction((n) => document.querySelector('.phase75-playhead-label')?.textContent === `T${n}`, turn);
}
try {
  for (const [name, settings] of Object.entries({ desktop: { viewport: {width:1440,height:900} }, phone: { viewport: {width:390,height:844}, isMobile:true, hasTouch:true } })) {
    const result = report.viewports[name] = { checks: [], messages: [], screenshots: [] };
    const context = await browser.newContext({ ...settings, locale:"en-US", deviceScaleFactor:1 });
    const page = await context.newPage();
    page.on("pageerror", e => result.messages.push(`pageerror: ${e.message}`));
    page.on("console", m => { if (m.type() === "error") result.messages.push(`console: ${m.text()}`); });
    try {
      await page.goto(url);
      await page.getByLabel("Open saved world file").setInputFiles(options.bundle);
      await page.waitForFunction((count) => document.querySelectorAll('.phase75-region-node').length === count && !!document.querySelector('.phase75-playhead-label') && !document.querySelector('.saved-world-loading'), expected.regions.length, {timeout:120000});
      await page.getByRole("tab",{name:"Livelihoods",exact:true}).click();
      await page.waitForFunction(() => document.querySelector('.systems-shell [role="tabpanel"]')?.getAttribute("aria-label") === "Livelihoods");
      for (const snapshot of snapshots) {
        if (options.journey === "history" && snapshot !== snapshots.at(-1)) continue;
        await seek(page,snapshot.turn);
        const section = page.getByRole("region",{ name: options.journey === "relief" ? "Poor relief services" : options.journey === "leagues" ? "Guild leagues" : options.journey === "branches" ? "Movement branches abroad" : "Linked histories", exact:true });
        await section.waitFor();
        const text = await section.innerText();
        check(result,`${name} snapshot${snapshot.turn}: panel mounts and has finite text`,!(/\bNaN\b|\bundefined\b|rejected as malformed/i.test(text)),text.slice(0,300));
        if (options.journey === "relief") {
          const f = snapshot.livelihoods.reform_services.frame;
          for (const p of f.purchases) {
            const row = section.getByRole("table",{name:`Relief purchases at snapshot ${snapshot.turn}`}).locator("tbody tr").filter({hasText:expected.regions[p.region]});
            const cells = await row.locator("td").allTextContents();
            check(result,`${name} snapshot${snapshot.turn}: actual relief payment region${p.region}`, cells[4] === units(p.food_milli) && cells[5] === fmt(p.rations) && cells[6] === units(p.credited_milli),JSON.stringify(cells));
          }
          for (const d of f.deliveries) {
            const rows = section.getByRole("table",{name:`Relief deliveries at snapshot ${snapshot.turn}`}).locator("tbody tr");
            const row = rows.filter({hasText:expected.regions[d.region]}).filter({has:page.locator("td").filter({hasText:String(d.bought_turn)})});
            const cells = await row.first().locator("td").allTextContents();
            const lowerUnknown = d.observed && d.delivered_at_least === null;
            check(result,`${name} snapshot${snapshot.turn}: actual bounded relief delivery region${d.region}`, cells[1] === String(d.bought_turn) && (!lowerUnknown || /at most.*no lower bound/.test(cells[4])),JSON.stringify(cells));
          }
          check(result,`${name} snapshot${snapshot.turn}: relief recipients remain regional`, text.includes("never attributed to persons") && (!f.purchases.length || text.includes("Recipients are not named")),text.slice(-250));
        } else if (options.journey === "leagues") {
          const f = snapshot.livelihoods.guild_leagues.frame;
          check(result,`${name}: natural league has actual payout witness`, f.payouts.length > 0,JSON.stringify(f.payouts));
          for (const p of f.payouts) {
            const rows = await section.getByRole("table",{name:`League claims at snapshot ${snapshot.turn}`}).locator("tbody tr").allTextContents();
            check(result,`${name}: actual city-purse claim league${p.league}`, rows.some((r)=>r.includes(units(p.loss_milli)) && r.includes(units(p.paid_milli)) && (!p.event_id || r.includes(p.event_id))),JSON.stringify(rows));
          }
          check(result,`${name}: league payout explicitly city's purse`,await section.getByRole("columnheader",{name:"Paid to the city's purse"}).count() === 1);
        } else if (options.journey === "branches") {
          check(result,`${name} snapshot${snapshot.turn}: parent recognizes the recorded branch package`,!(await page.getByRole("tabpanel",{name:"Livelihoods",exact:true}).innerText()).includes("names no package this viewer reads"));
          const record=snapshot.livelihoods.movement_branches;
          const actual=record.frame.rows.filter((r)=>r.status === "funded");
          check(result,`${name} snapshot${snapshot.turn}: natural named branch funding exists`,actual.length>0,JSON.stringify(actual));
          check(result,`${name} snapshot${snapshot.turn}: dated next-turn permission is described honestly`,text.includes(`Simulation turn ${record.source_turn}, mode ${record.mode}`)&&text.includes("available next turn")&&text.includes("No particular member's change is attributed"),text.slice(0,600));
          for(const r of actual){
            const row=section.getByRole("table",{name:`Movement branches at snapshot ${snapshot.turn}`}).locator("tbody tr").filter({has:page.locator("td").filter({hasText:new RegExp(`^${r.branch} / movement ${r.movement-1}$`)})});
            const cells=await row.locator("td").allTextContents();
            check(result,`${name} snapshot${snapshot.turn}: branch${r.branch} actual fee, payers and permission date`,cells[1]===`${r.host_name || `Polity ${r.host}`} / ${r.target_name || `Polity ${r.target}`}`&&cells[2]===String(r.members)&&cells[3].includes(`${(r.dues_milli/1000).toFixed(3)} from ${r.payers.length} people`)&&r.payers.every((id)=>cells[3].includes(String(id)))&&cells[4]===`Fee paid; permission available next turn (${r.active_from})`&&r.active_from===record.source_turn+1,JSON.stringify(cells));
            await row.getByText("Recorded payer ids",{exact:true}).click();
            check(result,`${name} snapshot${snapshot.turn}: branch${r.branch} named payers expand`,await row.locator("details").evaluate((d)=>d.open));
          }
          const r=actual.find((r)=>r.regions.length);
          if(r){
            const region=r.regions[0];
            await section.getByRole("button",{name:expected.regions[region],exact:true}).first().click();
            const investigation=page.getByRole("region",{name:"Selected region investigation",exact:true});
            await investigation.waitFor();
            check(result,`${name} snapshot${snapshot.turn}: branch region opens dated inspector`,(await investigation.innerText()).includes(`Region identity ${region}.`)&&(await investigation.innerText()).includes(`Recorded conditions · turn ${snapshot.turn}`));
          } else check(result,`${name} snapshot${snapshot.turn}: funded branch has region witness`,false);
        } else {
          const selector = section.getByLabel("Recorded entity");
          const opts = await selector.locator("option").evaluateAll((os)=>os.map((o)=>o.value));
          const person = opts.includes("person:13") ? "person:13" : opts.find((o)=>o.startsWith("person:"));
          check(result,`${name}: named person is selectable`,!!person,opts.slice(0,20).join(","));
          if (person) await selector.selectOption(person);
          const pointers = await section.locator("code").allTextContents();
          const resolves = (pointer) => {
            let value = expected;
            for (const token of pointer.slice(1).split("/")) { if (value == null || !(token in value)) return false; value=value[token]; }
            return value !== undefined;
          };
          check(result,`${name}: displayed source pointers exist in actual bundle`,pointers.length > 0 && pointers.every(resolves),pointers.join("\n"));
          check(result,`${name}: individual and regional evidence are visibly distinct`,(await section.innerText()).includes("Region only") && (await section.innerText()).includes("not this person's record"));
          const project = section.getByRole("button",{name:/^Project #\d+\s*$/}).first();
          if (await project.count()) {
            await project.click();
            check(result,`${name}: related project button changes stable-id entity`,(await selector.inputValue()).startsWith("project:"));
            const button = section.getByRole("button",{name:/^Snapshot \d+$/}).first();
            const turn = Number((await button.innerText()).replace("Snapshot ",""));
            await button.click();
            await page.waitForFunction((n)=>document.querySelector('.phase75-playhead-label')?.textContent === `T${n}`,turn);
            check(result,`${name}: history snapshot link seeks timeline`,await page.getByRole("slider",{name:"Historical turn"}).getAttribute("aria-valuenow") === String(turn));
          } else check(result,`${name}: linked project witness exists`,false);
        }
        await section.scrollIntoViewIfNeeded();
        const image = `${name}-snapshot${snapshot.turn}.png`;
        await page.screenshot({path:path.join(options.out,image)}); result.screenshots.push(image);
        const contentBounds = await section.evaluate((s)=>{
          const bounds=s.getBoundingClientRect();
          return [...s.querySelectorAll(".systems-note")].map((n)=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right,sectionLeft:bounds.left,sectionRight:bounds.right};});
        });
        check(result,`${name} snapshot${snapshot.turn}: explanatory text stays within section`,contentBounds.every((r)=>r.left>=r.sectionLeft-1 && r.right<=r.sectionRight+1),JSON.stringify(contentBounds));
        const width = await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth}));
        check(result,`${name} snapshot${snapshot.turn}: no horizontal document overflow`,width.page <= width.viewport + 1,JSON.stringify(width));
      }
      check(result,`${name}: no browser console or page errors`,result.messages.length===0,result.messages.join("\n"));
    } catch (e) { check(result,`${name}: journey completes`,false,e.stack); await page.screenshot({path:path.join(options.out,`${name}-failure.png`)}); }
    await context.close();
  }
} finally { await browser.close(); await new Promise((resolve)=>server.close(resolve)); writeFileSync(path.join(options.out,"report.json"),JSON.stringify({...report,failures},null,2)+"\n"); }
process.exitCode = failures ? 1 : 0;
