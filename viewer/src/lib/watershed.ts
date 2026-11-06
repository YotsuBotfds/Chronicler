import type { TurnSnapshot } from "../types";
import {
  WATERSHED_COLUMNS, type WatershedDrought, type WatershedFlood, type WatershedReading, type WatershedRecord,
} from "../watershedTypes";

/**
 * Strict reader of the watershed record (B1, `--watershed record_only`).
 * Disabled (off in the run), absent (on, missing at this snapshot), malformed
 * (with the reason), unobserved (no settled account this turn) and recorded
 * values (a zero is a recorded zero) stay distinct. Never reads final state.
 */

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const count = (x: unknown): x is number => Number.isInteger(x) && (x as number) >= 0;
const PHASES = ["temperate", "warming", "drought", "cooling"];
/** Record values are rounded to 6 decimals: identities hold to this relative tolerance. */
const TOLERANCE = 1e-5;
const close = (a: number, b: number, scale: number) => Math.abs(a - b) <= TOLERANCE * Math.max(1, scale);

/** Whether a snapshot carries a watershed record at all (a presence test; the reader parses). */
export function carriesWatershed(snapshot: TurnSnapshot | null | undefined): boolean {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null | undefined)?.livelihoods;
  return object(livelihoods) && livelihoods.watershed !== undefined && livelihoods.watershed !== null;
}

/** Whether any snapshot of the run carries the record (on); otherwise the switch was off. */
export function watershedOn(history: readonly TurnSnapshot[] | null | undefined): boolean {
  return Array.isArray(history) && history.some((snapshot) => carriesWatershed(snapshot));
}

function graphProblem(graph: unknown, regions: number): string | null {
  if (!object(graph) || graph.sea !== -1 || graph.sink !== -2 || !count(graph.river_steps)
    || !Array.isArray(graph.down) || graph.down.length !== regions) return "malformed drainage graph";
  const down = graph.down as unknown[];
  if (!down.every((d, i) => Number.isInteger(d) && (d as number) >= -2 && (d as number) < regions && d !== i))
    return "a region drains to an unknown region or to itself";
  for (let start = 0; start < regions; start += 1) {
    let node = start;
    for (let hops = 0; node >= 0; hops += 1) {
      if (hops > regions) return "the drainage graph has a cycle";
      node = down[node] as number;
    }
  }
  return null;
}

function floodProblem(x: unknown, regions: number, down: number[], turn: number): string | null {
  if (!object(x) || x.turn !== turn || !count(x.region) || x.region >= regions
    || ![x.excess, x.arrivals, x.channel, x.precipitation, x.inflow, x.external_in, x.storage_open, x.capacity].every(amount)
    || !(x.upstream_cover === null || amount(x.upstream_cover)) || !count(x.upstream_deforested)
    || !Array.isArray(x.tributaries)) return "malformed flood record";
  const f = x as unknown as WatershedFlood;
  if (!(f.excess > 0)) return "a flood record without an excess";
  if (!close(f.arrivals, f.precipitation + f.inflow + f.external_in, f.arrivals)) return "a flood's arrivals do not add up";
  if (!close(f.excess, f.arrivals - f.channel, f.arrivals)) return "a flood's excess is not arrivals minus channel";
  let sum = 0;
  for (const t of f.tributaries) {
    if (!Array.isArray(t) || t.length !== 2 || !count(t[0]) || t[0] >= regions || !amount(t[1]) || down[t[0]] !== f.region)
      return "a flood names a tributary that does not drain into it";
    sum += t[1];
  }
  return close(sum, f.inflow, f.inflow) ? null : "a flood's tributaries do not add up to its inflow";
}

function droughtProblem(x: unknown, regions: number, turn: number, ended: boolean): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions || !count(x.start_turn) || !count(x.turns) || x.turns < 1
    || ![x.min_fraction, x.precipitation, x.normal_precipitation, x.inflow, x.evaporation, x.withdrawal,
      x.upstream_withdrawal].every(amount) || !(x.upstream_cover === null || amount(x.upstream_cover))
    || !count(x.declared_turn)) return "malformed drought record";
  const d = x as unknown as WatershedDrought;
  if (d.start_turn > turn || (d.declared_turn as number) > turn || (d.declared_turn as number) < d.start_turn)
    return "a misdated drought";
  if (ended ? d.end_turn !== turn : d.end_turn !== null) return ended ? "an ended drought without its end turn" : "an open drought with an end";
  return null;
}

/** One snapshot's reading. `runOn`: whether any snapshot of the run carries the record. */
export function readWatershed(snapshot: TurnSnapshot | null | undefined, regionCount: number, runOn: boolean): WatershedReading {
  if (!carriesWatershed(snapshot)) return runOn ? { status: "absent" } : { status: "disabled" };
  const bad = (reason: string): WatershedReading => ({ status: "malformed", reason });
  const livelihoods = (snapshot as unknown as Record<string, Record<string, unknown>>).livelihoods;
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.watershed;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "B1" || x.mode !== "record_only") return bad("unknown watershed schema");
  const turn = snapshot!.turn;
  if (!count(x.source_turn) || x.source_turn + 1 !== turn || x.completed_turn !== turn) return bad("misdated observation");
  if (!count(x.opened_turn) || x.opened_turn > turn) return bad("misdated opening");
  if (!object(x.units) || !object(x.parameters)) return bad("malformed parameters");
  const why = graphProblem(x.graph, regionCount);
  if (why) return bad(why);
  const down = (x.graph as { down: number[] }).down;
  if (!Array.isArray(x.storage) || x.storage.length !== regionCount || !x.storage.every(amount)) return bad("malformed storage");
  if (!object(x.cumulative) || !Object.values(x.cumulative).every(finite)) return bad("malformed cumulative totals");
  if (!object(x.counters) || !Object.values(x.counters).every(count)) return bad("malformed counters");
  if (typeof x.observed !== "boolean") return bad("malformed observation flag");
  if (!x.observed) {
    return x.regions === null && x.floods === null && x.droughts === null && x.totals === null && x.phase === null
      ? { status: "unobserved", record: x as unknown as WatershedRecord } : bad("an unobserved turn with values");
  }
  if (typeof x.phase !== "string" || !PHASES.includes(x.phase)) return bad("unknown climate phase");
  const r = x.regions;
  if (!object(r)) return bad("malformed region columns");
  for (const key of WATERSHED_COLUMNS) {
    const column = r[key];
    if (!Array.isArray(column) || column.length !== regionCount || !column.every(amount)) return bad(`malformed column ${key}`);
  }
  const drought = r.drought_turns;
  if (!Array.isArray(drought) || drought.length !== regionCount || !drought.every(count)) return bad("malformed drought turns");
  const c = r as unknown as Record<string, number[]>;
  for (let i = 0; i < regionCount; i += 1) {
    if (c.index_observed[i] > 1 || c.index_derived[i] > 1) return bad("a water index above 1");
    if (c.storage[i] > c.capacity[i] + TOLERANCE) return bad("storage above capacity");
    if (c.external_out[i] > c.storage_open[i] + TOLERANCE) return bad("external outflow above storage");
    const opening = c.storage_open[i] + c.precipitation[i] + c.external_in[i] - c.external_out[i] + c.inflow[i];
    const scale = opening + c.evaporation[i] + c.withdrawal[i] + c.outflow[i];
    if (!close(c.storage[i], opening - c.evaporation[i] - c.withdrawal[i] - c.outflow[i], scale))
      return bad("a region's account does not close");
    let tributaries = 0;
    for (let u = 0; u < regionCount; u += 1) if (down[u] === i) tributaries += c.outflow[u];
    if (!close(tributaries, c.inflow[i], c.inflow[i])) return bad("an inflow is not the sum of its tributaries' outflows");
  }
  const t = x.totals;
  const keys = ["precipitation", "external_in", "external_out", "evaporation", "withdrawal", "to_sea", "to_sink", "transfer",
    "external_out_unmet", "storage_open", "storage_close", "closure_residual"];
  if (!object(t) || !keys.every((k) => finite(t[k]))) return bad("malformed totals");
  const totals = t as Record<string, number>;
  const net = totals.precipitation + totals.external_in - totals.external_out - totals.evaporation - totals.withdrawal
    - totals.to_sea - totals.to_sink;
  if (!close(totals.storage_close - totals.storage_open, net, totals.storage_open + totals.precipitation))
    return bad("the turn's account does not close");
  if (!Array.isArray(x.floods)) return bad("malformed floods");
  for (const f of x.floods) {
    const problem = floodProblem(f, regionCount, down, x.source_turn);
    if (problem) return bad(problem);
  }
  const d = x.droughts;
  if (!object(d) || !Array.isArray(d.open) || !Array.isArray(d.ended)) return bad("malformed droughts");
  for (const [list, ended] of [[d.open, false], [d.ended, true]] as const) {
    for (const spell of list) {
      const problem = droughtProblem(spell, regionCount, x.source_turn, ended);
      if (problem) return bad(problem);
    }
  }
  return { status: "ok", record: x as unknown as WatershedRecord };
}

/** Where a region drains, in words. */
export function drainsTo(down: number, names: readonly string[]): string {
  return down === -1 ? "the sea" : down === -2 ? "a closed basin (sink)" : names[down] ?? `region ${down}`;
}

export type WatershedRegionKey = "index_observed" | "index_derived" | "storage";

/** A region-history value from one snapshot, with the reason when there is none. */
export function watershedRegionValue(snapshot: TurnSnapshot, regionIndex: number, regionCount: number,
  key: WatershedRegionKey, runOn: boolean): { value: number | null; missing: string | null; path: string } {
  const reading = readWatershed(snapshot, regionCount, runOn);
  const path = `/livelihoods/watershed/regions/${key}/${regionIndex}`;
  if (regionIndex < 0) return { value: null, missing: "Region not in the watershed record", path };
  switch (reading.status) {
    case "disabled": return { value: null, missing: "Watershed off in this run (--watershed not recorded)", path };
    case "absent": return { value: null, missing: "Watershed not recorded at this snapshot", path };
    case "malformed": return { value: null, missing: `Malformed watershed record: ${reading.reason}`, path };
    case "unobserved":
      return key === "storage"
        ? { value: reading.record.storage[regionIndex], missing: null, path: `/livelihoods/watershed/storage/${regionIndex}` }
        : { value: null, missing: "Watershed account not settled this turn (unknown, not zero)", path };
    case "ok": return { value: reading.record.regions![key][regionIndex], missing: null, path };
  }
}
