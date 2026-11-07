import type { TurnSnapshot } from "../types";

/**
 * A3 workshop economics (``snapshot.livelihoods.workshop_economics``, stage
 * ``A3``): firms that buy their raw inputs, start with owner capital and sell
 * to academies and households. Money is in milli-units (1000 = one treasury
 * unit = one unit of a person's wealth); wares and inputs are milli-loads;
 * prices are milli-units per load. Types live here (``types.ts`` is pinned).
 *
 * States a reader keeps apart:
 * - ``absent``: no livelihoods record, or one without workshop payroll;
 * - ``disabled``: a workshop payroll (L6a) record without this record: the
 *   firms run under L6a's rules (free inputs, academy customers only);
 * - ``malformed``: a record that is not this shape or whose books do not close;
 * - ``unobserved``: the record has no receipts for its source turn (unknown, not zero);
 * - ``observed``: receipts whose zeros are recorded zeros (an empty list: no firm).
 */
export type WorkshopEconomicsStatus = "absent" | "disabled" | "malformed" | "unobserved" | "observed";

/**
 * One firm-turn's inputs. The plan price is the most recent positive raw price the
 * economy computed in an earlier tick (the firm's region, else its ruler's
 * realm), dated; the firm converts only what its reservation buys at that price
 * (``converted_unpaid_milli`` is always 0); the tick's own price is a diagnostic.
 */
export interface EconomicsInputs {
  plan_price_milli: number | null; plan_price_turn: number | null; plan_price_region: number | null;
  plan_price_source: "region" | "realm" | null; tick_price_milli: number | null;
  budget_milli: number | null; capacity_milli: number | null; need_milli: number | null;
  unbought_need_milli: number; crew: number; wage_bill_milli: number; no_input_reason: string | null;
  used_timber_milli: number; used_ore_milli: number; used_milli: number; cost_milli: number;
  charged_milli: number; not_charged_milli: number; converted_unpaid_milli: number;
  payee: [string, number | string] | null; treasury_units: number;
}

export interface EconomicsHouseholds {
  residents: number; households: number; demand_milli: number; commons_milli: number; gap_milli: number;
  offered_milli: number; price_milli: number | null; bought_milli: number; paid_milli: number;
  buying_households: number; priced_out_households: number; payers: number; depopulated: boolean;
}

export interface EconomicsReceiptRecord {
  turn: number; firm: number; region: number; owner: number | null; status: "open" | "closed"; operating: boolean;
  /** Null: the firm was not planned this turn (it opened in this turn's Phase 10). */
  inputs: EconomicsInputs | null;
  produced: number; titled: number; free_use_upper_bound: number; academy_sales: number; academy_sold: number;
  /** Null: no household round ran (a control mode, no controller, or no-customer payroll). */
  households: EconomicsHouseholds | null;
  customer_absent: string[]; capital_in: number; wages_due: number; wages_paid: number; owed_after: number;
  distributed: number; written_off: number; cash_open: number; cash_close: number; inventory_open: number;
  inventory_close: number; unsold_inventory: number; owner_asset_spend: number; idle_run: number;
  insolvent_run: number; event: string | null; worn: number; returned: number;
}

export interface FirmTermsRecord {
  firm: number; region: number; opened_turn: number; capital: number; capital_payer: number | null;
  status: "open" | "closed"; closed_turn: number | null; closed_reason: string | null; idle_run: number;
  turns: number; operating_turns: number; last_operating_turn: number | null; totals: Record<string, number>;
}

export interface WorkshopEconomicsRecord {
  schema_version: 1; stage: "A3"; mode: "market" | "free_inputs" | "academy_only"; source_turn: number;
  /** A3-2 (``--workshop-economics-rules 2``): firms hold their own output, never in the commons;
   * absent for rules version 1 (A3-1). */
  rules_version?: 2;
  units: { money: string; wares: string; price: string; milli: 1000 };
  firms: FirmTermsRecord[]; closed: FirmTermsRecord[];
  receipts: EconomicsReceiptRecord[] | null;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const MODES = ["market", "free_inputs", "academy_only"];
const ABSENCE = ["no_inventory", "no_controller", "no_academy", "academy_full", "commons_covers",
  "households_cannot_pay", "depopulated", "price_unknown", "academy_only_mode", "no_customer_mode"];

function validTerms(x: unknown, regions: number): boolean {
  return object(x) && count(x.firm) && count(x.region) && x.region < regions && count(x.opened_turn)
    && count(x.capital) && (x.status === "open" || x.status === "closed") && count(x.idle_run)
    && count(x.turns) && count(x.operating_turns) && object(x.totals) && Object.values(x.totals).every(count);
}

function validInputs(x: unknown): boolean {
  if (x === null) return true;
  if (!object(x)) return false;
  const ints = ["crew", "wage_bill_milli", "used_timber_milli", "used_ore_milli", "used_milli", "cost_milli",
    "charged_milli", "not_charged_milli", "converted_unpaid_milli", "unbought_need_milli"];
  if (!ints.every((k) => count(x[k]))) return false;
  for (const k of ["plan_price_milli", "plan_price_turn", "plan_price_region", "tick_price_milli", "capacity_milli",
    "need_milli"]) if (x[k] !== null && !count(x[k])) return false;
  if (x.plan_price_source !== null && x.plan_price_source !== "region" && x.plan_price_source !== "realm") return false;
  if (x.budget_milli !== null && !(finite(x.budget_milli) && Number.isInteger(x.budget_milli))) return false;
  const n = (k: string) => x[k] as number;
  // Nothing is converted unpaid; whatever is used was within what the plan price bought.
  if (n("converted_unpaid_milli") !== 0) return false;
  if (n("used_milli") > 0 && (x.plan_price_milli === null || x.capacity_milli === null
    || n("used_milli") > n("capacity_milli"))) return false;
  // The charge (or, in the cost control, the uncharged cost) is the cost at the plan price.
  if (n("charged_milli") + n("not_charged_milli") !== n("cost_milli") || n("charged_milli") * n("not_charged_milli") !== 0) {
    return false;
  }
  return true;
}

function validHouseholds(x: unknown): boolean {
  if (x === null) return true;
  if (!object(x)) return false;
  const ints = ["residents", "households", "demand_milli", "commons_milli", "gap_milli", "offered_milli",
    "bought_milli", "paid_milli", "buying_households", "priced_out_households", "payers"];
  if (!ints.every((k) => count(x[k])) || typeof x.depopulated !== "boolean") return false;
  if (x.price_milli !== null && !count(x.price_milli)) return false;
  // Bought within the offer, the offer within the gap the free commons left.
  return (x.bought_milli as number) <= (x.offered_milli as number) && (x.offered_milli as number) <= (x.gap_milli as number)
    && x.gap_milli === Math.max(0, (x.demand_milli as number) - (x.commons_milli as number));
}

function validReceipt(x: unknown, regions: number, source: number, owned = false): boolean {
  if (!object(x) || x.turn !== source || !count(x.firm) || !count(x.region) || x.region >= regions
    || typeof x.operating !== "boolean" || !validInputs(x.inputs) || !validHouseholds(x.households)
    || !Array.isArray(x.customer_absent) || !x.customer_absent.every((r) => ABSENCE.includes(r as string))) return false;
  const ints = ["produced", "titled", "free_use_upper_bound", "academy_sales", "academy_sold", "capital_in",
    "wages_due", "wages_paid", "owed_after", "worn", "returned", "distributed", "written_off", "cash_open",
    "cash_close", "inventory_open", "inventory_close", "unsold_inventory", "owner_asset_spend", "idle_run",
    "insolvent_run"];
  if (!ints.every((k) => count(x[k]))) return false;
  const n = (k: string) => x[k] as number;
  const inputs = x.inputs as EconomicsInputs | null;
  const households = x.households as EconomicsHouseholds | null;
  // Exact closures of the firm's cash and wares for the payroll pass (RS1 stipends come after it).
  return n("cash_close") === n("cash_open") + n("capital_in") + n("academy_sales") + (households?.paid_milli ?? 0)
      - (inputs?.charged_milli ?? 0) - n("wages_paid") - n("distributed") - n("written_off")
    && n("inventory_close") === n("inventory_open") + n("titled") - n("academy_sold") - (households?.bought_milli ?? 0)
      - n("worn") - n("returned")
    && n("unsold_inventory") === n("inventory_close") && n("titled") <= n("produced")
    // A3-2: the whole output is titled straight from the native column (no free use).
    && (!owned || (n("titled") === n("produced") && n("free_use_upper_bound") === 0));
}

function payrollPresent(livelihoods: Record<string, unknown>): boolean {
  return livelihoods.workshop_payroll != null;
}

/** The record's state at one snapshot, and the record when observed or unobserved. */
export function workshopEconomicsAt(snapshot: TurnSnapshot | null, regionCount: number):
  { status: WorkshopEconomicsStatus; record: WorkshopEconomicsRecord | null } {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return { status: "absent", record: null };
  if (!("workshop_economics" in livelihoods)) {
    return { status: payrollPresent(livelihoods) ? "disabled" : "absent", record: null };
  }
  const x = livelihoods.workshop_economics;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "A3" || !MODES.includes(x.mode as string)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn || !object(x.units) || x.units.milli !== 1000
    || !Array.isArray(x.firms) || x.firms.length > 4 || !x.firms.every((f) => validTerms(f, regionCount))
    || !Array.isArray(x.closed) || x.closed.length > 8 || !x.closed.every((f) => validTerms(f, regionCount))
    || !object(x.counters) || !Object.values(x.counters).every(count) || !object(x.parameters)
    || ("rules_version" in x && x.rules_version !== 2)) {
    return { status: "malformed", record: null };
  }
  const owned = x.rules_version === 2;
  if (x.receipts === null) return { status: "unobserved", record: x as unknown as WorkshopEconomicsRecord };
  if (!Array.isArray(x.receipts)
    || !x.receipts.every((r) => validReceipt(r, regionCount, x.source_turn as number, owned))) {
    return { status: "malformed", record: null };
  }
  return { status: "observed", record: x as unknown as WorkshopEconomicsRecord };
}

/** Milli-units (or milli-loads) as whole units. */
export const units = (milli: number) => milli / 1000;

export interface EconomicsFunnel {
  firmsOpened: number; capitalPaid: number; operatingFirmTurns: number; inputsCharged: number;
  unboughtNeed: number; realmPriceTurns: number; openingRefusedClosedCity: number; openingRefusedNoPrice: number;
  inputsNotCharged: number; academySales: number; householdSales: number; householdDelivered: number;
  pricedOutHouseholds: number; freeUseUpperBound: number; closedIdle: number; closedInsolvent: number;
  closedOther: number; assetSubsidyFirmUnits: number; sitesWithoutFirmTurns: number;
  householdShareOfSales: number | null;
  /** A3-2: output the firms took straight into inventory (null under rules version 1). */
  ownedOutput: number | null;
}

/** Lifetime funnel from the counters (units, not milli-units). Recorded zeros stay zeros. */
export function economicsFunnel(record: WorkshopEconomicsRecord): EconomicsFunnel {
  const c = (key: string) => record.counters[key] ?? 0;
  const academy = units(c("academy_sales"));
  const households = units(c("household_sales"));
  return {
    firmsOpened: c("firms_opened"), capitalPaid: units(c("capital_paid")), operatingFirmTurns: c("operating_firm_turns"),
    inputsCharged: units(c("inputs_charged")), inputsNotCharged: units(c("inputs_not_charged")),
    unboughtNeed: units(c("unbought_need")), realmPriceTurns: c("plan_price_realm_turns"),
    openingRefusedClosedCity: c("opening_refused_closed_city"), openingRefusedNoPrice: c("opening_refused_no_input_price"),
    academySales: academy, householdSales: households, householdDelivered: units(c("household_delivered")),
    pricedOutHouseholds: c("priced_out_households"), freeUseUpperBound: units(c("free_use_upper_bound")),
    closedIdle: c("closed_idle"), closedInsolvent: c("closed_insolvent"), closedOther: c("closed_other"),
    assetSubsidyFirmUnits: c("asset_subsidy_firm_units"), sitesWithoutFirmTurns: c("sites_without_firm_turns"),
    householdShareOfSales: academy + households > 0 ? households / (academy + households) : null,
    ownedOutput: record.rules_version === 2 ? units(c("owned_output")) : null,
  };
}
