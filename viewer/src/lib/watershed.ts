import type { TurnSnapshot } from "../types";
import {
  WATERSHED_COLUMNS, type WatershedDrought, type WatershedFlood, type WatershedGraph, type WatershedReading,
  type WatershedRecord, type WatershedStatic,
} from "../watershedTypes";

/**
 * Strict reader of the watershed record (B1, `--watershed record_only`).
 * Disabled (off in the run), absent (on, missing at this snapshot), malformed
 * (with the reason), unobserved (no settled account this turn) and recorded
 * values (a zero is a recorded zero) stay distinct. Every record carries its
 * static part (graph, parameters, units), so any segment of a history (a
 * state-file resume or a fork) reads on its own. Never reads final state.
 */

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const count = (x: unknown): x is number => Number.isInteger(x) && (x as number) >= 0;
const PHASES = ["temperate", "warming", "drought", "cooling"];
const FLOW_KEYS = ["precipitation", "external_in", "external_out", "evaporation", "withdrawal", "to_sea", "to_sink",
  "to_lake", "transfer"];
const CUMULATIVE_KEYS = [...FLOW_KEYS, "opening_storage", "storage", "closure_residual"];
const TOTAL_KEYS = [...FLOW_KEYS, "external_out_unmet", "external_in_coastal_flood", "external_in_unattributed",
  "external_out_unattributed", "storage_open", "storage_close", "closure_residual"];
/** Counters of flow mode only. */
const FLOW_COUNTER_KEYS = ["flood_consequences", "superseded_river_floods"];
/** In flow mode the native write-back rounds the index the account wrote to 4 decimals. */
export const NATIVE_ROUNDING = 5e-5;
const COUNTER_KEYS = ["planned_turns", "settled_turns", "abandoned_plans", "flood_region_turns", "drought_region_turns",
  "droughts_declared", "droughts_ended", "external_out_unmet_turns", "stale_baseline_turns"];
const SEA = -1;
const SINK = -2;
const LAKE = -3;
/**
 * Tolerances. The account closes in Python to `CLOSURE_TOLERANCE` (relative
 * 1e-9 of the gross terms, `chronicler.watershed`); the record rounds every
 * value to 6 decimals, so each carries at most `HALF_DIGIT` of rounding. An
 * identity over `terms` recorded values therefore holds to
 * `terms x HALF_DIGIT` plus the closure tolerance of its magnitude: the
 * allowance grows with the number of rounded values a check combines (a
 * derived outflow combines 8; a total over n regions 8n + 1), never with
 * an arbitrary margin.
 */
export const HALF_DIGIT = 5e-7;
export const CLOSURE_TOLERANCE = 1e-9;

/** Worst use of the allowance across the checks of one reading (diagnostics and tests). */
export interface WatershedAudit { worst: number; check: string }

function nearWith(audit: WatershedAudit | undefined) {
  return (check: string, a: number, b: number, terms: number, scale = 0): boolean => {
    const allowance = terms * HALF_DIGIT * (1 + 1e-9) + CLOSURE_TOLERANCE * Math.max(1, Math.abs(scale));
    const used = Math.abs(a - b) / allowance;
    if (audit && used > audit.worst) { audit.worst = used; audit.check = check; }
    return used <= 1;
  };
}
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
const sameKeys = (x: Record<string, unknown>, keys: string[]) =>
  Object.keys(x).length === keys.length && keys.every((k) => k in x);

/** Whether a snapshot carries a watershed record at all (a presence test; the reader parses). */
export function carriesWatershed(snapshot: TurnSnapshot | null | undefined): boolean {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null | undefined)?.livelihoods;
  return object(livelihoods) && "watershed" in livelihoods;
}

/** Whether any snapshot of the run carries the record (on); otherwise the switch was off. */
export function watershedOn(history: readonly TurnSnapshot[] | null | undefined): boolean {
  return Array.isArray(history) && history.some((snapshot) => carriesWatershed(snapshot));
}

function graphProblem(graph: unknown, regions: number): string | null {
  if (!object(graph) || graph.sea !== SEA || graph.sink !== SINK || graph.lake !== LAKE || !count(graph.river_steps)
    || !Array.isArray(graph.down) || graph.down.length !== regions) return "malformed drainage graph";
  const down = graph.down as unknown[];
  if (!down.every((d, i) => Number.isInteger(d) && (d as number) >= LAKE && (d as number) < regions && d !== i))
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

/** The run's reading context: whether any snapshot of the run carries the record. */
export interface WatershedRun {
  on: boolean;
}

/** Read once per run (history order does not matter). */
export function readWatershedRun(history: readonly TurnSnapshot[] | null | undefined): WatershedRun {
  return { on: watershedOn(history) };
}

/** Each region's outflow, derived (it is the residual of its account by construction). */
export function watershedOutflow(record: WatershedRecord): number[] | null {
  const c = record.regions;
  if (!c) return null;
  return c.storage.map((storage, i) => c.storage_open[i] + c.precipitation[i] + c.external_in[i] - c.external_out[i]
    + c.inflow[i] - c.evaporation[i] - c.withdrawal[i] - storage);
}

type Near = ReturnType<typeof nearWith>;

function consequenceProblem(x: unknown): string | null {
  if (!object(x) || !sameKeys(x, ["capacity_modifier", "cooldown", "soil_before", "soil_after"])
    || !finite(x.capacity_modifier) || !(x.capacity_modifier > 0 && x.capacity_modifier <= 1) || !count(x.cooldown)
    || x.cooldown < 1 || !amount(x.soil_before) || !amount(x.soil_after) || x.soil_after < x.soil_before)
    return "malformed flood consequence";
  return null;
}

function floodProblem(x: unknown, regions: number, down: number[], outflow: number[], turn: number, near: Near,
  flow: boolean): string | null {
  if (object(x) && flow !== ("consequence" in x)) return flow ? "a flow flood without its consequence" : "a record-only flood with a consequence";
  if (flow) { const why = consequenceProblem((x as Record<string, unknown>).consequence); if (why) return why; }
  if (!object(x) || x.turn !== turn || !count(x.region) || x.region >= regions
    || ![x.excess, x.arrivals, x.channel, x.precipitation, x.inflow, x.external_in, x.storage_open, x.capacity].every(amount)
    || !(x.upstream_cover === null || amount(x.upstream_cover)) || !count(x.upstream_deforested)
    || !Array.isArray(x.tributaries)) return "malformed flood record";
  const f = x as unknown as WatershedFlood;
  if (!(f.excess > 0)) return "a flood record without an excess";
  if (!near("flood arrivals", f.arrivals, f.precipitation + f.inflow + f.external_in, 4, f.arrivals))
    return "a flood's arrivals do not add up";
  if (!near("flood excess", f.excess, f.arrivals - f.channel, 3, f.arrivals)) return "a flood's excess is not arrivals minus channel";
  let total = 0;
  for (const t of f.tributaries) {
    if (!Array.isArray(t) || t.length !== 2 || !count(t[0]) || t[0] >= regions || !amount(t[1]) || down[t[0]] !== f.region)
      return "a flood names a tributary that does not drain into it";
    if (!near("flood tributary", t[1], outflow[t[0]], 9, t[1])) return "a flood's tributary outflow differs from the account";
    total += t[1];
  }
  return near("flood inflow", total, f.inflow, f.tributaries.length + 1, f.inflow)
    ? null : "a flood's tributaries do not add up to its inflow";
}

function droughtProblem(x: unknown, regions: number, turn: number, kind: "declared" | "ended"): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions || !count(x.start_turn) || !count(x.turns) || x.turns < 1
    || ![x.min_fraction, x.precipitation, x.normal_precipitation, x.inflow, x.evaporation, x.withdrawal,
      x.upstream_withdrawal].every(amount) || !(x.upstream_cover === null || amount(x.upstream_cover))
    || !count(x.declared_turn)) return "malformed drought record";
  const d = x as unknown as WatershedDrought;
  if (d.start_turn > turn || (d.declared_turn as number) > turn || (d.declared_turn as number) < d.start_turn)
    return "a misdated drought";
  if (kind === "declared" && (d.declared_turn !== turn || d.end_turn !== null)) return "a declared drought of another turn";
  if (kind === "ended" && d.end_turn !== turn) return "an ended drought without its end turn";
  return null;
}

function openDroughtProblem(x: unknown, regions: number, turn: number): string | null {
  if (!object(x) || !sameKeys(x, ["region", "start_turn", "turns", "declared_turn", "min_fraction"]) || !count(x.region)
    || x.region >= regions || !count(x.start_turn) || !count(x.turns) || x.turns < 1 || !count(x.declared_turn)
    || !amount(x.min_fraction)) return "malformed open drought";
  return x.start_turn > turn || x.declared_turn > turn || x.declared_turn < x.start_turn ? "a misdated drought" : null;
}

/** One snapshot's reading against its run (`readWatershedRun`). `audit` records the worst use of a tolerance. */
export function readWatershed(snapshot: TurnSnapshot | null | undefined, regionCount: number, run: WatershedRun,
  audit?: WatershedAudit): WatershedReading {
  const bad = (reason: string): WatershedReading => ({ status: "malformed", reason });
  const near = nearWith(audit);
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null | undefined)?.livelihoods;
  if (livelihoods !== undefined && livelihoods !== null && !object(livelihoods)) return bad("malformed livelihoods record");
  if (!carriesWatershed(snapshot)) return run.on ? { status: "absent" } : { status: "disabled" };
  const container = livelihoods as Record<string, unknown>;
  if (container.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = container.watershed;
  if (x === null) return bad("a null watershed record");
  if (!object(x) || x.schema_version !== 1
    || !((x.stage === "B1" && x.mode === "record_only") || (x.stage === "B2" && x.mode === "flow")))
    return bad("unknown watershed schema");
  const flow = x.mode === "flow";
  if (flow !== ("superseded" in x)) return bad(flow ? "a flow record without its superseded floods" : "a record-only record with superseded floods");
  const turn = snapshot!.turn;
  if (!count(x.source_turn) || x.source_turn + 1 !== turn || x.completed_turn !== turn) return bad("misdated observation");
  if (!count(x.opened_turn) || x.opened_turn > x.source_turn) return bad("misdated opening");
  const why = graphProblem(x.graph, regionCount);
  if (why) return bad(why);
  if (!object(x.parameters) || !object(x.units)) return bad("malformed parameters");
  const statics: WatershedStatic = { opened_turn: x.opened_turn, graph: x.graph as unknown as WatershedGraph,
    parameters: x.parameters as WatershedStatic["parameters"], units: x.units as Record<string, string> };
  const down = statics.graph.down;
  if (!object(x.counters) || !sameKeys(x.counters, flow ? [...COUNTER_KEYS, ...FLOW_COUNTER_KEYS] : COUNTER_KEYS)
    || !Object.values(x.counters).every(count))
    return bad("malformed counters");
  const cum = x.cumulative;
  if (!object(cum) || !sameKeys(cum, CUMULATIVE_KEYS) || !Object.values(cum).every(finite)) return bad("malformed cumulative totals");
  const k = cum as Record<string, number>;
  const cumNet = k.precipitation + k.external_in - k.external_out - k.evaporation - k.withdrawal - k.to_sea - k.to_sink - k.to_lake;
  if (!near("cumulative closure", k.storage - k.opening_storage, cumNet, 10, k.opening_storage + k.precipitation))
    return bad("the cumulative account does not close");
  if (typeof x.observed !== "boolean") return bad("malformed observation flag");
  if (!x.observed) {
    if (!Array.isArray(x.storage) || x.storage.length !== regionCount || !x.storage.every(amount)) return bad("malformed storage");
    if (!near("unobserved storage", sum(x.storage as number[]), k.storage, regionCount + 1, k.storage))
      return bad("storage differs from the cumulative account");
    return x.regions === null && x.floods === null && x.droughts === null && x.totals === null && x.external === null
      && x.phase === null && x.stale_baseline === null && (!flow || x.superseded === null)
      ? { status: "unobserved", record: x as unknown as WatershedRecord, statics } : bad("an unobserved turn with values");
  }
  if (x.storage !== null) return bad("a settled turn repeats its storage outside its columns");
  if (typeof x.phase !== "string" || !PHASES.includes(x.phase)) return bad("unknown climate phase");
  if (typeof x.stale_baseline !== "boolean") return bad("malformed stale-baseline flag");
  const r = x.regions;
  if (!object(r) || !sameKeys(r, [...WATERSHED_COLUMNS, "drought_turns"])) return bad("malformed region columns");
  for (const key of WATERSHED_COLUMNS) {
    const column = r[key];
    if (!Array.isArray(column) || column.length !== regionCount || !column.every(amount)) return bad(`malformed column ${key}`);
  }
  const drought = r.drought_turns;
  if (!Array.isArray(drought) || drought.length !== regionCount || !drought.every(count)) return bad("malformed drought turns");
  const record = x as unknown as WatershedRecord;
  const c = record.regions!;
  const outflow = watershedOutflow(record)!;
  for (let i = 0; i < regionCount; i += 1) {
    if (c.index_observed[i] > 1 || c.index_derived[i] > 1) return bad("a water index above 1");
    if (c.storage[i] > c.capacity[i] && !near("storage bound", c.storage[i], c.capacity[i], 2)) return bad("storage above capacity");
    if (c.external_out[i] > c.storage_open[i] && !near("external bound", c.external_out[i], c.storage_open[i], 2))
      return bad("external outflow above storage");
    const scale = c.storage_open[i] + c.precipitation[i] + c.external_in[i] + c.inflow[i];
    if (outflow[i] < 0 && !near("outflow sign", outflow[i], 0, 8, scale)) return bad("a region's account leaves a negative outflow");
    let tributaries = 0;
    let feeding = 0;
    for (let u = 0; u < regionCount; u += 1) if (down[u] === i) { tributaries += outflow[u]; feeding += 1; }
    if (!near("tributary inflow", tributaries, c.inflow[i], 8 * feeding + 1, c.inflow[i]))
      return bad("an inflow is not the sum of its tributaries' outflows");
  }
  const t = x.totals;
  if (!object(t) || !sameKeys(t, TOTAL_KEYS) || !Object.values(t).every(finite)) return bad("malformed totals");
  const totals = t as Record<string, number>;
  for (const [key, test] of [["to_sea", (d: number) => d === SEA], ["to_sink", (d: number) => d === SINK],
    ["to_lake", (d: number) => d === LAKE], ["transfer", (d: number) => d >= 0]] as const) {
    const members = outflow.filter((_, i) => test(down[i]));
    if (!near(key, totals[key], sum(members), 8 * members.length + 1, totals[key]))
      return bad(`the turn's ${key} differs from the regions' outflows`);
  }
  const net = totals.precipitation + totals.external_in - totals.external_out - totals.evaporation - totals.withdrawal
    - totals.to_sea - totals.to_sink - totals.to_lake;
  if (!near("turn closure", totals.storage_close - totals.storage_open, net, 10, totals.storage_open + totals.precipitation))
    return bad("the turn's account does not close");
  if (!near("turn storage", totals.storage_close, sum(c.storage), regionCount + 1, totals.storage_close)
    || !near("cumulative storage", k.storage, totals.storage_close, 2, k.storage))
    return bad("the turn's storage differs from its regions");
  if (!Array.isArray(x.external)) return bad("malformed external flows");
  const byRegion = { in: new Array<number>(regionCount).fill(0), out: new Array<number>(regionCount).fill(0) };
  const bySource: Record<string, number> = { in_coastal_flood: 0, in_unattributed: 0, out_unattributed: 0 };
  for (const e of x.external) {
    if (!object(e) || !sameKeys(e, ["region", "direction", "source", "amount"]) || !count(e.region) || e.region >= regionCount
      || !(e.direction === "in" || e.direction === "out") || !(e.source === "coastal_flood" || e.source === "unattributed")
      || !(amount(e.amount) && e.amount > 0) || (e.direction === "out" && e.source !== "unattributed"))
      return bad("malformed external flow");
    byRegion[e.direction][e.region] += e.amount;
    bySource[`${e.direction}_${e.source}`] += e.amount;
  }
  for (let i = 0; i < regionCount; i += 1) {
    // A region has at most two flows a direction (the flood's share and an unattributed remainder).
    if (!near("external in", byRegion.in[i], c.external_in[i], 3, c.external_in[i])
      || !near("external out", byRegion.out[i], c.external_out[i], 2, c.external_out[i]))
      return bad("external flows by source do not add up to the region's external flows");
  }
  if (x.stale_baseline && bySource.in_coastal_flood > 0) return bad("a stale baseline with attributed flows");
  for (const key of Object.keys(bySource)) {
    if (!near("external by source", bySource[key], totals[`external_${key}`], x.external.length + 1, totals[`external_${key}`]))
      return bad("external totals by source do not add up");
  }
  if (!Array.isArray(x.floods)) return bad("malformed floods");
  for (const f of x.floods) {
    const problem = floodProblem(f, regionCount, down, outflow, x.source_turn, near, flow);
    if (problem) return bad(problem);
  }
  if (flow) {
    if (!Array.isArray(x.superseded)) return bad("malformed superseded floods");
    for (const e of x.superseded) {
      if (!object(e) || !sameKeys(e, ["turn", "region", "duration"]) || e.turn !== x.source_turn || !count(e.region)
        || e.region >= regionCount || !count(e.duration) || e.duration < 1) return bad("malformed superseded flood");
    }
    for (let i = 0; i < regionCount; i += 1) {
      // The index the simulation used is the one the account wrote, up to the native rounding.
      if (!near("flow index", c.index_observed[i], c.index_derived[i], 2 + NATIVE_ROUNDING / HALF_DIGIT))
        return bad("in flow the index used differs from the derived index");
    }
  }
  const d = x.droughts;
  if (!object(d) || !sameKeys(d, ["declared", "open", "ended"]) || !Array.isArray(d.declared) || !Array.isArray(d.open)
    || !Array.isArray(d.ended)) return bad("malformed droughts");
  for (const [list, kind] of [[d.declared, "declared"], [d.ended, "ended"]] as const) {
    for (const spell of list) {
      const problem = droughtProblem(spell, regionCount, x.source_turn, kind);
      if (problem) return bad(problem);
    }
  }
  for (const spell of d.open) {
    const problem = openDroughtProblem(spell, regionCount, x.source_turn);
    if (problem) return bad(problem);
  }
  const openRegions = new Set((d.open as Array<{ region: number }>).map((s) => s.region));
  if (openRegions.size !== d.open.length) return bad("a region has two open droughts");
  if (!(d.declared as Array<{ region: number }>).every((s) => openRegions.has(s.region))) return bad("a declared drought is not open");
  return { status: "ok", record, statics };
}

/** Where a region drains, in words. */
export function drainsTo(down: number, names: readonly string[]): string {
  return down === SEA ? "the sea" : down === SINK ? "a closed basin (sink)" : down === LAKE ? "a lake (closed water)"
    : names[down] ?? `region ${down}`;
}

export type WatershedRegionKey = "index_observed" | "index_derived" | "storage";

/** A region-history value from one snapshot, with the reason when there is none. */
export function watershedRegionValue(snapshot: TurnSnapshot, regionIndex: number, regionCount: number,
  key: WatershedRegionKey, run: WatershedRun): { value: number | null; missing: string | null; path: string } {
  const path = `/livelihoods/watershed/regions/${key}/${regionIndex}`;
  if (regionIndex < 0) return { value: null, missing: "Region not in the watershed record", path };
  const reading = readWatershed(snapshot, regionCount, run);
  switch (reading.status) {
    case "disabled": return { value: null, missing: "Watershed off in this run (--watershed not recorded)", path };
    case "absent": return { value: null, missing: "Watershed not recorded at this snapshot", path };
    case "malformed": return { value: null, missing: `Malformed watershed record: ${reading.reason}`, path };
    case "unobserved":
      return key === "storage"
        ? { value: reading.record.storage![regionIndex], missing: null, path: `/livelihoods/watershed/storage/${regionIndex}` }
        : { value: null, missing: "Watershed account not settled this turn (unknown, not zero)", path };
    case "ok": return { value: reading.record.regions![key][regionIndex], missing: null, path };
  }
}
