#!/usr/bin/env node
/** Copy actual dated forecast observations from a decoded run; never invent missing records. */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [source, destination] = process.argv.slice(2);
if (!source) throw new Error("Usage: node scripts/build-harvest-observations.mjs DECODED_BUNDLE [OUTPUT]");
const bytes = readFileSync(source);
const bundle = JSON.parse(bytes);
if (!Array.isArray(bundle.history)) throw new Error("Expected decoded history (decode version-6 deltas first)");
const history = bundle.history.filter((row) => row.harvest_forecasts != null).map((row) => {
  if (row.harvest_forecasts.source_turn !== row.turn - 1) throw new Error(`Undated forecast summary at snapshot ${row.turn}`);
  return { turn: row.turn, harvest_forecasts: row.harvest_forecasts };
});
if (!history.length) throw new Error("The source contains no recorded harvest forecasts");
const fixture = { source: { seed: bundle.metadata?.seed, total_turns: bundle.metadata?.total_turns,
  sha256: createHash("sha256").update(bytes).digest("hex"),
  scope: "Actual native forecast observations only; standard world snapshots are not included." }, history };
writeFileSync(destination ?? fileURLToPath(new URL("../src/__fixtures__/harvest_forecast_observations.json", import.meta.url)),
  JSON.stringify(fixture) + "\n");
