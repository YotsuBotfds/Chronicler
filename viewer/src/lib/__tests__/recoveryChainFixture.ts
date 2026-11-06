/**
 * The recovery chain's natural records (template seed 23, eleven snapshots of the
 * chain of granary project 0 in region 7, Sapphire Coast; see the fixture's note)
 * as a bundle, and constructed variants of it (labelled in each test).
 */
import natural from "../../__fixtures__/recovery_chain_natural_records.json";
import type { Bundle } from "../../types";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Natural = { regions: string[]; civilizations: string[]; snapshots: Array<Record<string, any>> };
const NATURAL = natural as unknown as Natural;
export const REGIONS = NATURAL.regions;
export const TURNS = NATURAL.snapshots.map((s) => s.turn as number);
/** Region indices of the natural chain. */
export const SAPPHIRE = 7;
export const IRON_PEAKS = 1;

/** A bundle of the natural snapshots; ``edit`` may change each copied snapshot (constructed variants). */
export function chainBundle(edit?: (snapshot: Record<string, any>) => void): Bundle {
  const history = structuredClone(NATURAL.snapshots);
  if (edit) history.forEach(edit);
  return { world_state: { regions: REGIONS.map((name) => ({ name })), civilizations: NATURAL.civilizations.map((name) => ({ name })) },
    history } as unknown as Bundle;
}

export function snapshotOf(bundle: Bundle, turn: number) {
  return bundle.history.find((s) => s.turn === turn)!;
}

/** Drop packages from every snapshot (switched off for the run). */
export const without = (...keys: string[]) => (s: Record<string, any>) => {
  for (const k of keys) {
    if (k === "grain_storage") delete s.grain_reserves.storage;
    else delete s.livelihoods[k];
  }
};

// ---------------------------------------------------------------- constructed edits that keep each reader's books closed

type Rec = Record<string, any>;

/** Constructed: PL1 expedition ``eid``'s receipt becomes an unpaid turn, out of its civ's wage ledger. */
export function unpaidWoodcutting(s: Rec, eid: number) {
  const ts = s.livelihoods.timber_supply;
  const r = ts.receipts.find((x: Rec) => x.eid === eid);
  const l = ts.ledger.find((x: Rec) => x.civ === r.civ);
  l.expeditions -= 1; l.person_turns -= r.crew.length; l.wages_due_milli -= r.wages_due_milli;
  l.wages_applied_milli -= r.wages_milli; l.wage_residual_milli -= r.wage_residual_milli;
  l.charged = Math.max(0, Math.ceil((l.wages_applied_milli - l.prepaid_before_milli) / 1000));
  l.prepaid_after_milli = l.charged * 1000 + l.prepaid_before_milli - l.wages_applied_milli;
  if (l.expeditions === 0) ts.ledger = ts.ledger.filter((x: Rec) => x !== l);
  Object.assign(r, { unpaid: true, wages_due_milli: 0, wages_milli: 0, wage_residual_milli: 0 });
}

/** Constructed: the wealth ceiling refuses ``milli`` of PL3 member ``agent``'s wage on project ``pid`` (sunk instead). */
export function refusedWage(s: Rec, pid: number, agent: number, milli: number) {
  const rc = s.livelihoods.recovery_crews;
  const r = rc.receipts.find((x: Rec) => x.pid === pid);
  const m = r.members.find((x: Rec) => x.agent_id === agent);
  m.wage_milli -= milli; m.wage_residual_milli += milli;
  r.wages_milli -= milli; r.wage_residual_milli += milli; r.sunk_milli += milli;
  const l = rc.ledger.find((x: Rec) => x.civ === r.payer);
  l.wages_milli -= milli; l.wage_residual_milli += milli; l.sunk_milli += milli;
  const c = rc.counters;
  c.granary_wages_milli -= milli;
  c.granary_wage_residual_milli = (c.granary_wage_residual_milli ?? 0) + milli;
  c.granary_sunk_milli = (c.granary_sunk_milli ?? 0) + milli;
}

/** Constructed: a PL3 granary receipt in ``region`` with nobody on the crew (work planned, no free adult farmer). */
export function emptyGranaryCrew(s: Rec, pid: number, region: number) {
  const rc = s.livelihoods.recovery_crews;
  const payer = rc.receipts.find((x: Rec) => x.kind === "granary").payer;
  rc.receipts.push({ turn: s.turn - 1, pid, kind: "granary", region, payer, eligible: 0, eligible_site_city: null, planned: 1,
    capacity: 0, requested: 0, delivered: 0, members: [], coin_cost_milli: 0, wages_due_milli: 0, wages_milli: 0,
    wage_residual_milli: 0, sunk_milli: 0, farm_time_removed: 0 });
}

/** Constructed: an open RS2 workshop project ``pid`` (site ``asset``) in ``region``, listed first. */
export function workshopProject(s: Rec, pid: number, asset: number, region: number) {
  const rp = s.livelihoods.repair_projects;
  const base = rp.projects[0] ?? rp.closed[0];
  rp.projects.unshift({ ...base, pid, kind: "workshop", asset, region, settlement_id: 1, status: "open", closed_turn: null,
    closed_reason: null, delivered: 0, credited: 0, scope: 2, last_crew: [] });
}
