import type { TurnSnapshot } from "../types";
import {
  INFRA_DAMAGE_EVENTS, INFRA_END_CAUSES, INFRA_KINDS, INFRA_LIVE, INFRA_MODES, INFRA_REASONS, INFRA_TERMINAL,
  INFRA_WORK_MODES, type InfraAsset, type InfraConditionPoint, type InfraReading, type InfraReason, type InfraReceipt,
  type InfraRecord, type InfraWork, type InfraWorksStory,
} from "../infrastructureConditionTypes";

/**
 * Strict reader of B3 infrastructure condition
 * (`livelihoods.infrastructure_condition`). Disabled (off in the run), absent
 * (on, missing at this snapshot), malformed (with the reason), an unsettled
 * frame (unknown, not zero), a mode without works and recorded values (a zero
 * is a recorded zero) stay distinct. Never reads final state.
 */

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const count = (x: unknown): x is number => Number.isInteger(x) && (x as number) >= 0;
const unit = (x: unknown): x is number => amount(x) && x <= 1;
const civ = (x: unknown): x is number => Number.isInteger(x) && (x as number) >= -1;
const one = <T extends string>(list: readonly T[], x: unknown): x is T => typeof x === "string" && (list as readonly string[]).includes(x);
const EPS = 1e-9;
/** Condition at which service is full (`chronicler.infrastructure_condition.SERVICE_FULL`). */
export const SERVICE_FULL = 0.5;
export const serviceOf = (condition: number) => Math.min(1, Math.max(0, condition) / SERVICE_FULL);

/** Whether a snapshot carries the record at all (a presence test; the reader parses). */
export function carriesInfrastructure(snapshot: TurnSnapshot | null | undefined): boolean {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null | undefined)?.livelihoods;
  return object(livelihoods) && "infrastructure_condition" in livelihoods;
}

/** Whether any snapshot of the run carries the record (on); otherwise the switch was off. */
export function infrastructureOn(history: readonly TurnSnapshot[] | null | undefined): boolean {
  return Array.isArray(history) && history.some((snapshot) => carriesInfrastructure(snapshot));
}

function historyProblem(x: unknown): boolean {
  return !Array.isArray(x) || !x.every((e) => Array.isArray(e) && e.length === 4 && count(e[0]) && typeof e[1] === "string"
    && Number.isInteger(e[2]) && Number.isInteger(e[3]));
}

function assetProblem(x: unknown, regions: number, live: boolean, forced: boolean, turn: number): string | null {
  if (!object(x) || !count(x.aid) || !one(INFRA_KINDS, x.kind) || !count(x.region) || x.region >= regions
    || !count(x.record_index) || !count(x.built_turn) || typeof x.builder_civ !== "string" || !count(x.opened_turn)
    || !unit(x.condition) || !count(x.status_turn) || !civ(x.responsible) || ![x.wear, x.damage, x.credited].every(amount)
    || !(x.failed_turn === null || count(x.failed_turn)) || !(x.food_at_risk === null || amount(x.food_at_risk))
    || historyProblem(x.history) || !unit(x.service)
    || !unit(x.condition_service)) return "malformed asset";
  if (x.opened_turn > turn || x.status_turn > turn) return "a misdated asset";
  if (live) {
    if (!one(INFRA_LIVE, x.status) || x.cause !== null) return "a live asset with a terminal status";
    if ((x.status === "failed") !== (x.condition === 0)) return "an asset's status disagrees with its condition";
    if (Math.abs(x.condition_service - serviceOf(x.condition)) > EPS) return "an asset's service is not min(1, condition / 0.5)";
    if (Math.abs(x.service - (forced ? 1 : x.condition_service)) > EPS) return "an asset's applied service disagrees with its mode";
  } else if (!one(INFRA_TERMINAL, x.status) || !one(INFRA_END_CAUSES, x.cause) || x.service !== 1 || x.condition_service !== 0) {
    return "a terminal asset without its end";
  }
  return null;
}

function workProblem(x: unknown, regions: number, open: boolean): string | null {
  if (!object(x) || !count(x.wid) || !count(x.aid) || !one(INFRA_KINDS, x.kind) || !count(x.region) || x.region >= regions
    || typeof x.cause !== "string" || !count(x.opened_turn) || !unit(x.opened_condition) || !civ(x.controller)
    || ![x.scope, x.delivered, x.credited, x.timber_used].every(amount) || !count(x.coin_cost_milli)
    || !count(x.work_turns) || !count(x.stalled_turns) || !object(x.stalls) || !Array.isArray(x.damages)
    || historyProblem(x.history)) return "malformed work";
  if (!Object.entries(x.stalls).every(([k, v]) => one(INFRA_REASONS, k) && count(v))) return "malformed work stalls";
  const w = x as unknown as InfraWork;
  if (w.credited > w.delivered + EPS) return "a work credited more than it delivered";
  if (open) {
    if (w.status !== "open" || w.closed_turn !== null || w.delivered > w.scope + 1e-6) return "an open work beyond its scope";
  } else if (!(w.status === "completed" || w.status === "abandoned") || !count(w.closed_turn)) {
    return "a closed work without its close";
  }
  return null;
}

function receiptProblem(x: unknown, regions: number, turn: number): string | null {
  if (!object(x) || x.turn !== turn || !count(x.wid) || !count(x.aid) || !one(INFRA_KINDS, x.kind) || !count(x.region)
    || x.region >= regions || !civ(x.payer) || !(x.status === "progress" || x.status === "stalled")
    || !Array.isArray(x.reasons) || !x.reasons.every((r) => one(INFRA_REASONS, r))
    || ![x.requested, x.delivered, x.credited, x.granary_request, x.timber_held, x.timber_used, x.timber_returned,
      x.remaining_after].every(amount) || typeof x.shared !== "boolean" || !count(x.coin_cost_milli)
    || !(x.envelope === null || count(x.envelope)) || !unit(x.condition_before) || !unit(x.condition_after))
    return "malformed receipt";
  const r = x as unknown as InfraReceipt;
  if (r.delivered > r.requested + 1e-6) return "a receipt delivered beyond its request";
  if ((r.status === "progress") !== (r.delivered > 0)) return "a receipt's status disagrees with its work";
  if (Math.abs(r.timber_held - r.timber_used - r.timber_returned) > 1e-6) return "a receipt's timber does not close";
  if (r.status === "stalled" && r.reasons.length === 0) return "a stalled receipt without a reason";
  return null;
}

function ledgerProblem(x: unknown, turn: number): string | null {
  if (!object(x) || x.turn !== turn || !count(x.civ) || !count(x.works) || !amount(x.work_delivered)
    || !amount(x.timber_used) || ![x.coin_cost_milli, x.charged, x.prepaid_before_milli, x.prepaid_after_milli, x.rs2_charged]
      .every(count) || !(x.envelope === null || count(x.envelope))) return "malformed ledger";
  if ((x.prepaid_before_milli as number) >= 1000 || (x.prepaid_after_milli as number) >= 1000
    || (x.charged as number) * 1000 + (x.prepaid_before_milli as number)
      !== (x.coin_cost_milli as number) + (x.prepaid_after_milli as number)) return "a ledger row does not close";
  if (x.envelope !== null && (x.charged as number) > (x.envelope as number))
    return "the works spent beyond their envelope";
  return null;
}

/** One snapshot's reading. `on`: whether the run records the switch (`infrastructureOn`). */
export function readInfrastructure(snapshot: TurnSnapshot | null | undefined, regionCount: number, on: boolean): InfraReading {
  const bad = (reason: string): InfraReading => ({ status: "malformed", reason });
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null | undefined)?.livelihoods;
  if (livelihoods !== undefined && livelihoods !== null && !object(livelihoods)) return bad("malformed livelihoods record");
  if (!carriesInfrastructure(snapshot)) return on ? { status: "absent" } : { status: "disabled" };
  const container = livelihoods as Record<string, unknown>;
  if (container.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = container.infrastructure_condition;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "B3" || !one(INFRA_MODES, x.mode)) return bad("unknown infrastructure schema");
  const turn = snapshot!.turn;
  if (!count(x.source_turn) || x.source_turn + 1 !== turn) return bad("misdated observation");
  const works = one(INFRA_WORK_MODES, x.mode);
  if (x.works_enabled !== works) return bad("a works flag that disagrees with the mode");
  if (!Array.isArray(x.assets) || !Array.isArray(x.terminal) || !Array.isArray(x.works) || !Array.isArray(x.closed)
    || !Array.isArray(x.damages) || !object(x.counters) || !Object.values(x.counters).every(amount) || !object(x.prepaid)
    || !count(x.sink_milli) || !object(x.parameters) || !object(x.units)) return bad("malformed record");
  const forced = x.mode === "record_only";
  const seen = new Set<number>();
  for (const [list, live] of [[x.assets, true], [x.terminal, false]] as const) {
    for (const a of list) {
      const why = assetProblem(a, regionCount, live, forced, x.source_turn);
      if (why) return bad(why);
      const aid = (a as InfraAsset).aid;
      if (seen.has(aid)) return bad("an asset id appears twice");
      seen.add(aid);
    }
  }
  const live = new Set((x.assets as InfraAsset[]).map((a) => a.aid));
  const wids = new Set<number>();
  for (const [list, open] of [[x.works, true], [x.closed, false]] as const) {
    for (const w of list) {
      const why = workProblem(w, regionCount, open);
      if (why) return bad(why);
      const work = w as InfraWork;
      if (wids.has(work.wid)) return bad("a work id appears twice");
      wids.add(work.wid);
      if (open && !live.has(work.aid)) return bad("an open work on an asset that no longer serves");
    }
  }
  if (!works && (x.works as unknown[]).length > 0) return bad("works in a mode without works");
  for (const d of x.damages as unknown[]) {
    if (!object(d) || !count(d.did) || !count(d.turn) || !count(d.aid) || !one(INFRA_KINDS, d.kind) || !count(d.region)
      || !one(INFRA_DAMAGE_EVENTS, d.event) || !amount(d.amount) || !unit(d.condition_before) || !unit(d.condition_after)
      || Math.abs(d.condition_before - d.condition_after - d.amount) > 1e-9) return bad("malformed damage");
  }
  if (x.skipped_damages !== undefined && (!Array.isArray(x.skipped_damages) || !x.skipped_damages.every((d) => object(d)
    && count(d.turn) && count(d.aid) && count(d.region) && one(INFRA_DAMAGE_EVENTS, d.event) && amount(d.amount)
    && count(d.kept)))) return bad("malformed skipped damage");
  const frame = [x.receipts, x.ledger, x.unmet, x.shared];
  if (frame.every((v) => v === null)) {
    return { status: "ok", frame: works ? "unsettled" : "no_works", record: x as unknown as InfraRecord };
  }
  if (!Array.isArray(x.unmet) || !Array.isArray(x.shared)) return bad("a partial frame");
  if (!works) return x.receipts === null && x.ledger === null
    ? { status: "ok", frame: "no_works", record: x as unknown as InfraRecord } : bad("receipts in a mode without works");
  if (!Array.isArray(x.receipts) || !Array.isArray(x.ledger)) {
    return x.receipts === null && x.ledger === null
      ? { status: "ok", frame: "unsettled", record: x as unknown as InfraRecord } : bad("a partial frame");
  }
  for (const r of x.receipts) {
    const why = receiptProblem(r, regionCount, x.source_turn);
    if (why) return bad(why);
  }
  for (const row of x.ledger) {
    const why = ledgerProblem(row, x.source_turn);
    if (why) return bad(why);
  }
  return { status: "ok", frame: "settled", record: x as unknown as InfraRecord };
}

/** Each asset's condition at every readable snapshot (malformed or absent snapshots are skipped, not zero). */
export function conditionSeries(history: readonly TurnSnapshot[] | null | undefined, regionCount: number)
  : Map<number, InfraConditionPoint[]> {
  const out = new Map<number, InfraConditionPoint[]>();
  if (!Array.isArray(history)) return out;
  for (const snapshot of history) {
    const reading = readInfrastructure(snapshot, regionCount, true);
    if (reading.status !== "ok") continue;
    for (const a of [...reading.record.assets, ...reading.record.terminal]) {
      const points = out.get(a.aid) ?? [];
      const point = { turn: snapshot.turn, condition: a.condition, status: a.status };
      if (points.length === 0 || points[points.length - 1].turn !== point.turn) points.push(point);
      out.set(a.aid, points);
    }
  }
  return out;
}

/**
 * The run's most stalled work up to `upTo` (inclusive): the underfunded
 * public works story, read only from recorded works, assets and stalls.
 * Null when no work stalled.
 */
export function worksStory(history: readonly TurnSnapshot[] | null | undefined, regionCount: number, upTo: number)
  : InfraWorksStory | null {
  if (!Array.isArray(history)) return null;
  let best: InfraWorksStory | null = null;
  const failed = new Map<number, number>();
  for (const snapshot of history) {
    if (snapshot.turn > upTo) continue;
    const reading = readInfrastructure(snapshot, regionCount, true);
    if (reading.status !== "ok") continue;
    const assets = new Map([...reading.record.assets, ...reading.record.terminal].map((a) => [a.aid, a]));
    for (const a of assets.values()) if (a.failed_turn !== null) failed.set(a.aid, a.failed_turn);
    for (const work of [...reading.record.works, ...reading.record.closed]) {
      if (work.stalled_turns === 0) continue;
      if (best === null || work.stalled_turns > best.work.stalled_turns
        || (work.stalled_turns === best.work.stalled_turns && work.wid === best.work.wid)) {
        const stalls = (Object.entries(work.stalls) as Array<[InfraReason, number]>).sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
        best = { work, asset: assets.get(work.aid) ?? null, seen_turn: snapshot.turn, failed_turn: null, stalls };
      }
    }
  }
  if (best !== null) best.failed_turn = failed.get(best.work.aid) ?? null;
  return best;
}
