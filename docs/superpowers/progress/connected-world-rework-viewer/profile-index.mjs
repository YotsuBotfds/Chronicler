#!/usr/bin/env node
/** Production-code index diagnostic. No simulation and no observation edits. */
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";
const options = { "source-root": null, bundle: null, out: null };
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, "");
  if (!(key in options) || !process.argv[i + 1]) throw new Error(`Invalid option ${process.argv[i]}`);
  options[key] = path.resolve(process.argv[i + 1]);
}
if (Object.values(options).some(v => !v)) throw new Error("Required: --source-root CHECKOUT --bundle FILE --out FILE");
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const root = options["source-root"], require = createRequire(path.join(root, "viewer/package.json"));
const source = path.join(root, "viewer/src/lib/entityHistory.ts");
const sourceHash = sha(readFileSync(source));
const { build } = require("esbuild");
const compiled = await build({ stdin: { contents:
  `export {decodeBundlePayload} from ${JSON.stringify(path.join(root, "viewer/src/lib/bundleCodec.ts"))};\nexport {indexEntityHistory,entityHistory,entityKey} from ${JSON.stringify(source)};`,
  resolveDir: root, loader: "ts" }, bundle: true, platform: "node", format: "esm", write: false });
mkdirSync(path.dirname(options.out), { recursive: true });
const moduleFile = options.out + ".runtime.mjs";
writeFileSync(moduleFile, compiled.outputFiles[0].contents);
const { decodeBundlePayload, indexEntityHistory, entityHistory, entityKey } = await import(pathToFileURL(moduleFile).href);
const timings = {}, mark = (name, fn) => { const started = performance.now(), result = fn(); timings[name] = performance.now() - started; return result; };
const raw = mark("read", () => readFileSync(options.bundle));
const parsed = mark("JSON.parse", () => JSON.parse(raw.toString("utf8")));
const bundle = mark("decode", () => decodeBundlePayload(parsed));
const formatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });
const primitives = [-Infinity, -123456789.1234567, -.0005, -.00001, -0, 0, .0005, .09490852802991867, 1.23456789, 123456789.1234567, Infinity, NaN];
const primitive_equivalence = primitives.map(value => ({ value: Object.is(value, -0) ? "-0" : String(value),
  legacy: value.toLocaleString(undefined, { maximumFractionDigits: 3 }), reused: formatter.format(value) }));
if (primitive_equivalence.some(row => row.legacy !== row.reused)) throw new Error("Number formatting changed");
let formatCount = 0, formatMs = 0;
const original = Number.prototype.toLocaleString;
Number.prototype.toLocaleString = function (...args) { const started = performance.now(), result = original.apply(this, args); formatCount++; formatMs += performance.now() - started; return result; };
let index;
try { index = mark("indexEntityHistory", () => indexEntityHistory(bundle)); } finally { Number.prototype.toLocaleString = original; }
const available = mark("availableEntities", () => {
  const named = new Map();
  for (const { frames } of index.snapshots) for (const frame of Object.values(frames)) for (const row of frame.rows)
    for (const item of [row.entity, ...row.related, ...(row.region === null ? [] : [{ kind: "region", id: row.region }])]) named.set(entityKey(item), item);
  return [...named.values()].sort((a, b) => a.kind.localeCompare(b.kind) || String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
});
const through = Math.max(...index.snapshots.map(s => s.snapshot.turn));
const person = mark("person13", () => entityHistory(index, { kind: "person", id: 13 }, through));
const region = mark("region3", () => entityHistory(index, { kind: "region", id: 3 }, through));
const digest = createHash("sha256");
for (const s of index.snapshots) digest.update(JSON.stringify({ turn: s.snapshot.turn, epoch: s.epoch, frames: s.frames }));
digest.update(JSON.stringify(index.entities));
const queries = createHash("sha256");
for (const e of [{ kind: "person", id: 13 }, { kind: "person", id: 999999 }, { kind: "household", id: 13 }, { kind: "region", id: 3 },
  { kind: "project", id: 0 }, { kind: "timber_order", id: 0 }, { kind: "army", id: "army-2" }])
  for (const t of [1, 27, 66, through]) queries.update(JSON.stringify(entityHistory(index, e, t)));
if (sha(readFileSync(source)) !== sourceHash) throw new Error("Source changed during diagnostic");
const result = { source, source_sha256: sourceHash, compiled_sha256: sha(compiled.outputFiles[0].contents),
  bundle: options.bundle, bundle_sha256: sha(raw), bundle_bytes: raw.length,
  locale: formatter.resolvedOptions(), primitive_equivalence, timings_ms: timings,
  diagnostic_toLocaleString_calls: formatCount, diagnostic_toLocaleString_ms: formatMs,
  index_sha256: digest.digest("hex"), queries_sha256: queries.digest("hex"),
  snapshots: index.snapshots.length, observations: index.snapshots.reduce((n, s) => n + Object.values(s.frames).reduce((a, f) => a + f.rows.length, 0), 0),
  entities: index.entities.length, available: available.length, person_rows: person.length, region_rows: region.length,
  node_rss_bytes: process.memoryUsage().rss,
  note: "Formatting wrapper is diagnostic overhead. Browser timings are the primary user-facing measurements. No input/data reduction." };
writeFileSync(options.out, JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result));
