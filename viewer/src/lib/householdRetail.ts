import type { TurnSnapshot } from "../types";

/**
 * L6b household food retail (``snapshot.livelihoods.household_retail``,
 * ``--household-retail``, default off): the completed turn's frame written by
 * ``household_retail.snapshot_summary``. Shapes and identities:
 * docs/integration/household-retail.md (Python, Accounting, Native).
 *
 * Food is in whole milli-food (1000 = one food unit = two rations at the
 * default ration), money in whole milli-units (1000 = one wealth unit),
 * rations in fractions of one ration. ``null`` is unknown, never zero.
 */

export const RETAIL_GOODS = ["grain", "fish", "salt", "botanicals", "exotic"] as const;
export const RETAIL_MODES = ["retail", "no_relief", "free_exchange", "record_only"] as const;
/** ``schedule`` (A2R): a frozen schedule (``--household-retail-schedule``): exact intervals
 * ``{region: [[open, close], ..., [open, null]]}`` (S1), or the approximate first-turn
 * ``{region: opening turn}`` map. */
export const RETAIL_BOUNDARIES = ["market", "paid_work", "all", "schedule"] as const;
export type RetailMode = typeof RETAIL_MODES[number];
export type RetailBoundary = typeof RETAIL_BOUNDARIES[number];
/** The modes, plainly. */
export const RETAIL_MODE_LABEL: Record<RetailMode, string> = {
  retail: "retail",
  no_relief: "no_relief (what relief protects)",
  free_exchange: "free_exchange (ownership without cash)",
  record_only: "record_only (identity control, nothing applied)",
};
/** Flows of the owned pool (``FLOW_KINDS``) and their signs in close = open + Σ sign × flow. */
export const FLOW_SIGNS = {
  titled: 1, own_eaten: -1, sold: -1, procured: -1, decay: -1, overflow: -1, war_loss: -1, to_commons: -1,
  inherited_in: 1, inherited_out: -1,
  /** Rules version 2 (A2R, RL4): owned grain above the storage cap, lost before Phase 10 procurement. */
  cap_overflow: -1,
  /** A4 titled trade: owners' surplus bought by a merchant (title passes to its shipment), and a
   * shipment's cargo becoming its holder's claim at the destination or back at the origin. */
  sold_merchant: -1, consigned_in: 1, returned_in: 1,
} as const;
export type FlowKind = keyof typeof FLOW_SIGNS;
const FLOW_KINDS = Object.keys(FLOW_SIGNS) as FlowKind[];
/** Why owned food went to the region's commons (``COMMONS_REASONS``). */
export const COMMONS_REASONS = ["untitled", "claims_refused", "escheat", "pilot_closed", "pool_reset", "switch_off"] as const;
export type CommonsReason = typeof COMMONS_REASONS[number];
export const RECORD_KINDS = ["pilot_opened", "pilot_closed", "war_loss", "inherited", "escheat", "pool_reset",
  "claims_refused", "switch_off"] as const;
/** Person statuses in the native provisioning sample, in code order. */
export const RETAIL_STATUSES = ["fed", "priced_out", "offer_short", "withheld_dead"] as const;
const NATIVE_MODES: Record<string, number> = { retail: 0, no_relief: 1, free_exchange: 2 };
const SAMPLE_COLUMNS = ["agent_id", "region", "household", "ration", "fair_share", "status"];
const MAX_SAMPLE = 24;
const MAX_LOG = 64;
/** The economy's Phase 2 retail columns per pilot region (food units). */
export const PHASE2_COLUMNS = [
  ...["titled", "owned_close", "owned_decay", "owned_overflow"].flatMap((kind) => RETAIL_GOODS.map((g) => `retail_${kind}_${g}`)),
  "commons_consumed", "commons_sufficiency",
];
/** The native provisioning row (``RETAIL_REGION_COLUMNS``) as Python copies it. */
export const PROVISIONING_COLUMNS = [
  "region", "mode", "phase2_alive", "persons", "households", "children", "sufficiency", "fair_share",
  "price_quoted_milli", "price_milli", "milli_food_per_ration", "free_rations", "free_living", "free_given",
  "free_unallocated", "free_to_priority", "priority_households", "claims", "present_claims", "withheld_dead_claims",
  "offered_milli", "withheld_dead_milli", "own_eaten_milli", "own_eaten_fair_milli", "own_eaten_open_milli",
  "sold_milli", "sold_fair_milli", "sold_open_milli", "unsold_milli", "demand_fair_milli", "demand_open_milli",
  "buying_households", "sellers", "paid_milli", "credited_milli", "refunded_milli", "refused_ceiling_milli",
  "rations", "fed_fair", "full_ration", "min_ration", "max_ration", "deficit",
  "priced_out_households", "priced_out_persons", "priced_out_children", "priced_out_deficit",
  "offer_short_households", "offer_short_persons", "offer_short_children", "offer_short_deficit",
  "withheld_dead_households", "withheld_dead_persons", "withheld_dead_children", "withheld_dead_deficit",
] as const;
export type ProvisioningColumn = typeof PROVISIONING_COLUMNS[number];
export type RetailProvisioning = Record<ProvisioningColumn, number>;
/** Columns that are whole numbers (counts, milli-food, milli-units). */
const WHOLE = PROVISIONING_COLUMNS.filter((k) => k.endsWith("_milli") || /^(region|mode|phase2_alive|persons|households|children|claims|present_claims|withheld_dead_claims|buying_households|sellers|fed_fair|full_ration)$/.test(k)
  || /_(households|persons|children)$/.test(k));
/** People below their fair share, by cause: a cash limit, an offer short of it, a dead owner's claim withheld. */
export const RISKS = ["priced_out", "offer_short", "withheld_dead"] as const;
export type Risk = typeof RISKS[number];

export interface RetailWouldBe {
  titled_milli: number; owners: number; farmers: number; untitled_milli: number;
  /** Absent when the turn's agent tick did not price the region. */
  price_milli?: number;
}

/** One pilot region's completed turn (``RegionFrame``). */
export interface RetailRegionFrame {
  region: number; opened_turn: number; open_milli: number; close_milli: number; goods_close: number[]; owners: number;
  /** This turn's owned-pool flows; a flow that did not happen is left out (it closes the identity). */
  flows: Partial<Record<FlowKind, number>>;
  commons: Partial<Record<CommonsReason, number>>;
  /** Null: nothing was installed for the region this turn (unknown, not zero). */
  price_milli: number | null; free_rations: number | null;
  phase2: Record<string, number> | null;
  /** Null: the region was not provisioned this turn (record_only, or the tick took no install). */
  provisioning: RetailProvisioning | null;
  would_be: RetailWouldBe | null;
  /** Null with an observed income receipt: none of the region's farmers had a row. */
  income_replaced: number | null; income_rows: number | null;
  merchant_food_departing: number | null; owned_food_unloadable_milli: number | null;
}

export interface RetailLogRecord {
  turn: number; region: number; kind: typeof RECORD_KINDS[number]; milli: number;
  owner: number | null; other: number | null; note: string | null;
}

export type RetailSampleRow = [number, number, number, number, number, number];

export interface HouseholdRetailRecord {
  schema_version: 1; stage: "L6b"; mode: RetailMode; boundary: RetailBoundary; source_turn: number;
  /** Null: the source turn's frame was not recorded (unknown, not zero). */
  regions: RetailRegionFrame[] | null;
  money: Record<string, number> | null; income: Record<string, number> | null;
  sample: RetailSampleRow[] | null; sample_dropped: number | null; sample_columns: string[];
  log: RetailLogRecord[]; log_dropped: number;
  counters: Record<string, number>; income_replaced_total: number;
  parameters: { theta: number; price_floor: number; price_cap: number; max_claims: number; units: string; goods: string[] };
}

export type HouseholdRetailReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: HouseholdRetailRecord };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const near = (a: number, b: number, tol: number) => Math.abs(a - b) <= tol;
/** Python's ration tolerance (f64 sums of f32 rations, rounded to 6 decimals). */
const RATION_TOL = 1e-4;
const flow = (r: RetailRegionFrame, k: FlowKind) => r.flows[k] ?? 0;
const commons = (r: RetailRegionFrame, k: CommonsReason) => r.commons[k] ?? 0;
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

function provisioningProblem(p: Record<string, unknown>, frame: RetailRegionFrame, mode: RetailMode): string | null {
  if (!PROVISIONING_COLUMNS.every((k) => finite(p[k]))) return "malformed provisioning row";
  const q = p as unknown as RetailProvisioning;
  if (!WHOLE.every((k) => count(q[k]))) return "provisioning counts or milli columns are not whole";
  if (![q.sufficiency, q.fair_share, q.free_rations, q.free_living, q.free_given, q.free_to_priority, q.rations,
    q.min_ration, q.max_ration, q.deficit, q.priced_out_deficit, q.offer_short_deficit, q.withheld_dead_deficit]
    .every((v) => v >= -RATION_TOL)) return "a negative ration in the provisioning row";
  if (q.region !== frame.region) return "a provisioning row names another region";
  if (q.mode !== NATIVE_MODES[mode]) return "the provisioning mode differs from the record's mode";
  const freeTol = RATION_TOL * Math.max(1, q.free_rations);
  const personTol = RATION_TOL * Math.max(1, q.persons);
  // Installed price and free rations, and the food debited from the claims.
  if (frame.price_milli === null || frame.free_rations === null || q.price_milli !== frame.price_milli
    || !near(q.free_rations, frame.free_rations, freeTol)) return "the provisioning row differs from the install";
  if (q.own_eaten_milli !== flow(frame, "own_eaten") || q.sold_milli !== flow(frame, "sold"))
    return "the claims debited differ from the food eaten and sold";
  // Food: free_given + free_unallocated = free_rations; own_eaten + sold + unsold = offered.
  if (!near(q.free_given + q.free_unallocated, q.free_rations, freeTol) || q.free_unallocated < -freeTol)
    return "free food does not close (free_given + free_unallocated = free_rations)";
  if (q.own_eaten_milli + q.sold_milli + q.unsold_milli !== q.offered_milli)
    return "owned food on offer does not close (own_eaten + sold + unsold = offered)";
  if (q.own_eaten_fair_milli + q.own_eaten_open_milli !== q.own_eaten_milli || q.sold_fair_milli + q.sold_open_milli !== q.sold_milli)
    return "the fair-share and open rounds do not add up";
  if (q.withheld_dead_milli > q.unsold_milli || q.withheld_dead_claims > q.claims || q.present_claims > q.claims
    || (q.withheld_dead_milli > 0) !== (q.withheld_dead_claims > 0)) return "withheld claims exceed the unsold";
  if (q.milli_food_per_ration <= 0) return "malformed ration size";
  if (!near(q.rations, q.free_given + (q.own_eaten_milli + q.sold_milli) / q.milli_food_per_ration, personTol))
    return "person rations do not close (rations = free_given + (own_eaten + sold) / ration)";
  if (q.rations > q.persons + personTol || (q.persons > 0 && (q.min_ration > q.max_ration + 1e-9 || q.max_ration > 1 + RATION_TOL)))
    return "a ration above one";
  // People: every provisioned person is fed to the fair share or recorded with one cause.
  if (q.fed_fair + q.priced_out_persons + q.offer_short_persons + q.withheld_dead_persons !== q.persons)
    return "people do not close (fed + priced out + offer short + withheld = persons)";
  if (q.households > q.persons || q.children > q.persons || q.full_ration > q.persons) return "more households or children than persons";
  for (const k of RISKS) {
    const [h, n, c, d] = [q[`${k}_households`], q[`${k}_persons`], q[`${k}_children`], q[`${k}_deficit`]];
    if (c > n || h > n || h > q.households || c > q.children || (n === 0) !== (h === 0)) return `malformed ${k.replace(/_/g, " ")} counts`;
    if (n === 0 && d > 1e-6) return `a ${k.replace(/_/g, " ")} deficit without people`;
  }
  if (!near(q.deficit, q.priced_out_deficit + q.offer_short_deficit + q.withheld_dead_deficit, personTol))
    return "the deficit does not close (priced out + offer short + withheld)";
  if (q.withheld_dead_persons > 0 && q.withheld_dead_claims === 0) return "people short of a withheld claim without one";
  // Money: paid = credited + refunded; refunds are the ceiling's refusals; each household pays ceil(bought × price / ration).
  if (q.paid_milli !== q.credited_milli + q.refunded_milli) return "payments do not balance (paid = credited + refunded)";
  if (q.refunded_milli !== q.refused_ceiling_milli) return "refunds differ from the ceiling's refusals";
  if (mode === "free_exchange") {
    if (q.price_milli !== 0 || q.paid_milli !== 0 || q.priced_out_persons !== 0) return "the free-exchange control charged for food";
  } else if (!(q.sold_milli * q.price_milli <= q.paid_milli * q.milli_food_per_ration
    && q.paid_milli * q.milli_food_per_ration <= q.sold_milli * q.price_milli + q.buying_households * q.milli_food_per_ration))
    return "paid differs from sold × price / ration beyond per-household rounding";
  if (q.buying_households > q.households || (q.sold_milli > 0) !== (q.sellers > 0)) return "malformed buyers or sellers";
  return null;
}

function regionProblem(x: unknown, regions: number, mode: RetailMode, source: number): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions || !count(x.opened_turn) || x.opened_turn > source
    || !count(x.open_milli) || !count(x.close_milli) || !Array.isArray(x.goods_close) || x.goods_close.length !== RETAIL_GOODS.length
    || !x.goods_close.every(count) || !count(x.owners) || !object(x.flows) || !object(x.commons)) return "malformed pilot region";
  if (!Object.entries(x.flows).every(([k, v]) => FLOW_KINDS.includes(k as FlowKind) && count(v))) return "malformed owned-food flows";
  if (!Object.entries(x.commons).every(([k, v]) => COMMONS_REASONS.includes(k as CommonsReason) && count(v)))
    return "malformed commons reasons";
  if (!(x.price_milli === null || count(x.price_milli)) || !(x.free_rations === null || amount(x.free_rations))
    || !(x.income_replaced === null || amount(x.income_replaced)) || !(x.income_rows === null || count(x.income_rows))
    || (x.income_replaced === null) !== (x.income_rows === null)
    || !(x.merchant_food_departing === null || amount(x.merchant_food_departing))
    || !(x.owned_food_unloadable_milli === null || count(x.owned_food_unloadable_milli))
    || (x.merchant_food_departing === null) !== (x.owned_food_unloadable_milli === null)
    || (x.price_milli === null) !== (x.free_rations === null)) return "malformed pilot region";
  const r = x as unknown as RetailRegionFrame;
  // The owned pool closes: close = open + titled − own_eaten − sold − procured − decay − overflow − war_loss − to_commons
  // + inherited_in − inherited_out, and the goods sum to the close.
  if (r.open_milli + sum(FLOW_KINDS.map((k) => FLOW_SIGNS[k] * flow(r, k))) !== r.close_milli)
    return "the owned food does not close (close = open + titled − eaten − sold − procured − decay − overflow − war loss − to commons)";
  if (sum(r.goods_close) !== r.close_milli) return "the owned goods do not sum to the close";
  if ((r.close_milli === 0) !== (r.owners === 0) || r.owners > r.close_milli) return "owners and owned food disagree";
  if (flow(r, "inherited_in") !== flow(r, "inherited_out")) return "inheritance does not conserve claims";
  if (sum(COMMONS_REASONS.map((k) => commons(r, k))) !== flow(r, "to_commons")) return "food to the commons does not match its reasons";
  if (commons(r, "untitled") + commons(r, "claims_refused") > flow(r, "titled")) return "more title kept commons than titled";
  if (r.owned_food_unloadable_milli !== null && r.owned_food_unloadable_milli !== r.close_milli)
    return "the owned food merchants could not load differs from the owned close";
  if (r.phase2 !== null) {
    if (!object(r.phase2) || !PHASE2_COLUMNS.every((k) => amount((r.phase2 as Record<string, unknown>)[k])))
      return "malformed Phase 2 columns";
    const p = r.phase2;
    const titled = 1000 * sum(RETAIL_GOODS.map((g) => p[`retail_titled_${g}`]));
    if (!near(titled, flow(r, "titled"), RETAIL_GOODS.length)) return "the title differs from the economy's titled columns";
    for (const kind of ["decay", "overflow"] as const) {
      if (flow(r, kind) > 1000 * sum(RETAIL_GOODS.map((g) => p[`retail_owned_${kind}_${g}`])) + RETAIL_GOODS.length)
        return `more owned ${kind} applied than the economy reported`;
    }
  }
  if (mode === "record_only") {
    // It holds no food: nothing is titled, eaten, sold or returned, and nothing is installed.
    if (r.open_milli || r.close_milli || Object.keys(r.flows).length || Object.keys(r.commons).length
      || r.price_milli !== null || r.provisioning !== null || r.phase2 !== null || r.income_replaced !== null)
      return "the record-only control held, sold or priced food";
    if (r.would_be !== null) {
      const w = r.would_be as unknown as Record<string, unknown>;
      if (!object(w) || ![w.titled_milli, w.owners, w.farmers, w.untitled_milli].every(amount)
        || !(w.price_milli === undefined || count(w.price_milli)) || (w.owners as number) > (w.farmers as number)
        || (w.untitled_milli as number) > (w.titled_milli as number)) return "malformed would-be title";
    }
    return null;
  }
  if (r.would_be !== null) return "a would-be title outside the record-only control";
  if (r.provisioning !== null) {
    if (!object(r.provisioning)) return "malformed provisioning row";
    const why = provisioningProblem(r.provisioning as unknown as Record<string, unknown>, r, mode);
    if (why) return `region ${r.region}: ${why}`;
  } else if (flow(r, "own_eaten") || flow(r, "sold")) return "food eaten or sold without a provisioning row";
  if (mode === "free_exchange" && r.income_replaced !== null) return "the free-exchange control replaced farm income";
  return null;
}

function logProblem(x: unknown, regions: number, turn: number): string | null {
  if (!object(x) || !count(x.turn) || x.turn > turn || !count(x.region) || x.region >= regions
    || !RECORD_KINDS.includes(x.kind as never) || !count(x.milli) || !(x.owner === null || count(x.owner))
    || !(x.other === null || count(x.other)) || !(x.note === null || typeof x.note === "string")) return "malformed record";
  return null;
}

/** Strict reading: absent, malformed (with the reason) or a dated record whose books close. */
export function readHouseholdRetail(snapshot: TurnSnapshot | null, regionCount: number): HouseholdRetailReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.household_retail === undefined || livelihoods.household_retail === null)
    return { status: "absent" };
  const bad = (reason: string): HouseholdRetailReading => ({ status: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.household_retail;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "L6b" || !RETAIL_MODES.includes(x.mode as RetailMode)
    || !RETAIL_BOUNDARIES.includes(x.boundary as RetailBoundary)) return bad("unknown household-retail schema");
  const mode = x.mode as RetailMode;
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  const p = x.parameters;
  if (!object(p) || !finite(p.theta) || p.theta < 0 || p.theta > 1 || (mode === "no_relief") !== (p.theta === 1)
    || !amount(p.price_floor) || !finite(p.price_cap) || p.price_cap < p.price_floor || !count(p.max_claims)
    || typeof p.units !== "string" || !Array.isArray(p.goods) || p.goods.join() !== RETAIL_GOODS.join())
    return bad("malformed parameters");
  if (!object(x.counters) || !Object.values(x.counters).every(count)) return bad("malformed counters");
  const c = x.counters as Record<string, number>;
  const get = (k: string) => c[k] ?? 0;
  if (get("paid_milli") !== get("credited_milli") + get("refunded_milli")) return bad("lifetime payments do not balance");
  if (mode === "free_exchange" && (get("paid_milli") || get("procurement_credited_milli")))
    return bad("the free-exchange control moved money");
  if (!amount(x.income_replaced_total) || (mode === "free_exchange" && x.income_replaced_total > 0))
    return bad("malformed lifetime income replaced");
  if (!Array.isArray(x.log) || x.log.length > MAX_LOG || !count(x.log_dropped)) return bad("malformed record log");
  for (const [i, entry] of x.log.entries()) {
    const why = logProblem(entry, regionCount, snapshot!.turn);
    if (why) return bad(why);
    if (i > 0 && (entry as RetailLogRecord).turn < (x.log[i - 1] as RetailLogRecord).turn) return bad("the record log is out of order");
  }
  if (!Array.isArray(x.sample_columns) || x.sample_columns.join() !== SAMPLE_COLUMNS.join()) return bad("malformed sample columns");
  const frame = [x.regions, x.money, x.income, x.sample, x.sample_dropped];
  if (frame.some((v) => v === null) !== frame.every((v) => v === null)) return bad("a partial frame");
  if (x.regions !== null) {
    if (!Array.isArray(x.regions) || !object(x.money) || !object(x.income) || !Array.isArray(x.sample)
      || x.sample.length > MAX_SAMPLE || !count(x.sample_dropped)) return bad("malformed frame");
    for (const r of x.regions) {
      const why = regionProblem(r, regionCount, mode, x.source_turn);
      if (why) return bad(why);
    }
    const regions = x.regions as RetailRegionFrame[];
    if (!regions.every((r, i) => i === 0 || r.region > regions[i - 1].region)) return bad("pilot regions listed twice or out of order");
    // Money: the region rows add up to the turn's money rows, which balance.
    const money = x.money as Record<string, unknown>;
    if (!Object.values(money).every(count)) return bad("malformed money");
    const m = money as Record<string, number>;
    const provisioned = regions.filter((r) => r.provisioning !== null);
    const paidKeys = ["paid_milli", "credited_milli", "refunded_milli", "rows"];
    if (paidKeys.some((k) => k in m) !== paidKeys.every((k) => k in m) || paidKeys.every((k) => k in m) !== provisioned.length > 0)
      return bad("money rows without provisioning");
    if (provisioned.length) {
      const total = (k: ProvisioningColumn) => sum(provisioned.map((r) => r.provisioning![k]));
      if (m.paid_milli !== m.credited_milli + m.refunded_milli) return bad("the turn's payments do not balance");
      if (m.paid_milli !== total("paid_milli") || m.credited_milli !== total("credited_milli") || m.refunded_milli !== total("refunded_milli"))
        return bad("money rows differ from the region totals");
    }
    const procurementKeys = ["procurement_flows", "procurement_owed_milli", "procurement_credited_milli",
      "procurement_residual_milli", "procurement_unpaid_milli"];
    const procured = sum(regions.map((r) => flow(r, "procured")));
    if (procurementKeys.some((k) => k in m) !== procurementKeys.every((k) => k in m)) return bad("a partial procurement credit");
    if (procurementKeys.every((k) => k in m)) {
      if (m.procurement_owed_milli !== m.procurement_credited_milli + m.procurement_residual_milli + m.procurement_unpaid_milli)
        return bad("procurement credits do not close (owed = credited + refused + unpaid)");
      if (mode === "free_exchange" ? m.procurement_credited_milli + m.procurement_residual_milli !== 0 : m.procurement_unpaid_milli !== 0)
        return bad(mode === "free_exchange" ? "the free-exchange control paid owners for granary grain" : "owners' granary grain left unpaid");
      if ((m.procurement_flows > 0) !== (procured > 0)) return bad("granary purchases of owners' grain and their credits disagree");
    } else if (procured > 0) return bad("owners' grain bought by granaries without a credit");
    // Income: the receipt's rows by region, plus the unattributed.
    const income = x.income as Record<string, unknown>;
    const replaces = mode === "retail" || mode === "no_relief";
    if (Object.keys(income).length) {
      if (!replaces || !count(income.rows) || !amount(income.replaced) || !amount(income.unattributed)) return bad("malformed income receipt");
      const byRegion = sum(regions.map((r) => r.income_replaced ?? 0));
      if (!near(byRegion + (income.unattributed as number), income.replaced as number, 1e-5 * Math.max(1, regions.length, income.replaced as number))
        || sum(regions.map((r) => r.income_rows ?? 0)) > (income.rows as number)) return bad("income replaced differs from its rows");
    } else if (regions.some((r) => r.income_replaced !== null)) return bad("income replaced without a receipt");
    else if (replaces && provisioned.length) return bad("provisioning without its income receipt");
    const shown = new Set(provisioned.map((r) => r.region));
    if (!(x.sample as unknown[]).every((s) => Array.isArray(s) && s.length === 6 && count(s[0]) && count(s[1]) && shown.has(s[1])
      && count(s[2]) && amount(s[3]) && s[3] <= 1 + RATION_TOL && amount(s[4]) && s[4] <= 1 + RATION_TOL && count(s[5]) && s[5] < RETAIL_STATUSES.length))
      return bad("malformed person sample");
  }
  return { status: "ok", record: x as unknown as HouseholdRetailRecord };
}

/** The owned share of a region's title (the title less what stayed commons: no farmers, or the claims cap). */
export function ownedTitle(r: RetailRegionFrame): number {
  return flow(r, "titled") - commons(r, "untitled") - commons(r, "claims_refused");
}

/** The harvest's commons share implied by the title and θ (derived; null at θ = 0). */
export function commonsShare(r: RetailRegionFrame, theta: number): number | null {
  return theta > 0 ? flow(r, "titled") * (1 - theta) / theta : null;
}

export interface RiskTotals { households: number; persons: number; children: number; deficit: number }
/** This turn's people below their fair share, by cause, over provisioned regions; null when none was provisioned. */
export function riskTotals(record: HouseholdRetailRecord): Record<Risk, RiskTotals> | null {
  const rows = (record.regions ?? []).flatMap((r) => r.provisioning ? [r.provisioning] : []);
  if (!rows.length) return null;
  const out = {} as Record<Risk, RiskTotals>;
  for (const k of RISKS) {
    out[k] = { households: sum(rows.map((p) => p[`${k}_households`])), persons: sum(rows.map((p) => p[`${k}_persons`])),
      children: sum(rows.map((p) => p[`${k}_children`])), deficit: sum(rows.map((p) => p[`${k}_deficit`])) };
  }
  return out;
}

export function flowOf(r: RetailRegionFrame, k: FlowKind): number { return flow(r, k); }
export function commonsOf(r: RetailRegionFrame, k: CommonsReason): number { return commons(r, k); }
