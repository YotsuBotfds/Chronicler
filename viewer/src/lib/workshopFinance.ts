import { readLivelihoodRecord } from "./livelihoodRecord";
import { isRecord as object, finite, amount, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/**
 * L6a workshop payroll (``snapshot.livelihoods.workshop_payroll``). Money is
 * in milli-units (1000 = one treasury unit = one native wealth unit); wares
 * are in milli-loads. Every account closes exactly in integers.
 */
export interface OwedWageRecord { agent_id: number; amount: number; since_turn: number }

export interface WorkshopFirmRecord {
  site: number; region: number; settlement_id: number; city_name: string; opened_turn: number;
  status: "open" | "closed"; closed_turn: number | null; closed_reason: string | null;
  cash: number; inventory: number; owed: OwedWageRecord[]; hours: number; crew_cap: number;
  insolvent_run: number; diverted: number; totals: Record<string, number>;
  history: Array<[number, string, number]>;
}

export interface PayrollReceiptRecord {
  turn: number; site: number; region: number; controller: number | null; operating: boolean;
  hours: number; crew_cap: number; crew: number[]; shares: number[];
  output: number | null; title_basis: number | null; titled: number;
  cash_open: number; inventory_open: number; customers: number; sold: number; sales: number;
  wages_due: number; wages_paid: number; wages_cap_residual: number; owed_lapsed: number; owed_after: number;
  /** Null: no wealth-phase observation of the replaced ordinary income (unknown, not zero). */
  income_replaced: number | null;
  worn: number; returned: number; distributed: number; written_off: number;
  cash_close: number; inventory_close: number; insolvent: boolean;
  hours_next: number | null; crew_cap_next: number | null; event: string | null;
  /** RS1 apprentice stipends paid from cash after the payroll pass; absent unless one was paid. */
  stipends?: number;
  /** A3 workshop economics (absent otherwise): owner capital received, inputs paid, household sales and wares. */
  capital?: number; inputs?: number; household_sales?: number; household_sold?: number;
}

export interface MoneyTransferRecord {
  id: string; turn: number; phase: "phase2" | "phase10";
  kind: "sale" | "wage" | "distribution" | "write_off" | "stipend" | "capital" | "input_purchase" | "household_sale";
  payer: [string, number]; payee: [string, number]; amount: number; applied: number; residual: number; status: string;
}

export interface MaterialTransferRecord {
  id: string; turn: number; phase: "phase2" | "phase10"; kind: "title" | "delivery" | "wear" | "return" | "household_delivery";
  source: [string, number]; dest: [string, number]; good: string; requested: number; delivered: number; status: string;
}

export interface WorkshopFinanceRecord {
  schema_version: 1; stage: "L6a"; mode: "paid" | "unpaid_labor" | "no_customer"; source_turn: number;
  units: { money: string; wares: string; milli: 1000 };
  firms: WorkshopFirmRecord[]; closed: WorkshopFirmRecord[];
  /** Null: no completed payroll pass for the source turn (unknown, not zero). */
  receipts: PayrollReceiptRecord[] | null;
  transfers: { money: MoneyTransferRecord[]; materials: MaterialTransferRecord[] } | null;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

const MODES = ["paid", "unpaid_labor", "no_customer"];
// A3 (workshop economics) appends capital, input purchases, household sales and deliveries.
const MONEY = ["sale", "wage", "distribution", "write_off", "stipend", "capital", "input_purchase", "household_sale"];
const MATERIAL = ["title", "delivery", "wear", "return", "household_delivery"];
const account = (x: unknown) => Array.isArray(x) && x.length === 2 && typeof x[0] === "string" && finite(x[1]);

function total(totals: Record<string, unknown>, key: string): number | null {
  const v = totals[key];
  return v === undefined ? 0 : count(v) ? v : null;
}

function validFirm(x: unknown, regions: number): boolean {
  if (!object(x) || !count(x.site) || !count(x.region) || x.region >= regions || typeof x.city_name !== "string"
    || !count(x.opened_turn) || (x.status !== "open" && x.status !== "closed") || !count(x.cash)
    || !count(x.inventory) || !finite(x.hours) || x.hours <= 0 || x.hours > 1 || !count(x.crew_cap)
    || x.crew_cap < 1 || x.crew_cap > 8 || !count(x.insolvent_run) || !Array.isArray(x.owed)
    || x.owed.length > 16 || !x.owed.every((o) => object(o) && count(o.agent_id) && count(o.amount))
    || !object(x.totals)) return false;
  const t = (key: string) => total(x.totals as Record<string, unknown>, key);
  const keys = ["sales", "wages", "distributed", "written_off", "titled", "delivered", "worn", "returned",
    "stipends", "capital", "inputs", "household_sales", "household_delivered"];
  if (keys.some((k) => t(k) === null)) return false;
  // Exact closure of the firm's accounts (RS1 stipends and A3's capital, inputs and household sales: absent is zero).
  return x.cash === t("capital")! + t("sales")! + t("household_sales")! - t("inputs")! - t("wages")!
      - t("distributed")! - t("written_off")! - t("stipends")!
    && x.inventory === t("titled")! - t("delivered")! - t("household_delivered")! - t("worn")! - t("returned")!;
}

function validReceipt(x: unknown, regions: number, source: number): boolean {
  if (!object(x) || x.turn !== source || !count(x.site) || !count(x.region) || x.region >= regions
    || !Array.isArray(x.crew) || x.crew.length > 8 || !x.crew.every(count) || !Array.isArray(x.shares)
    || x.shares.length !== x.crew.length || !x.shares.every((s) => finite(s) && s > 0 && s <= 1)) return false;
  const ints = ["titled", "cash_open", "inventory_open", "customers", "sold", "sales", "wages_due", "wages_paid",
    "wages_cap_residual", "owed_lapsed", "owed_after", "worn", "returned", "distributed", "written_off",
    "cash_close", "inventory_close"];
  if (!ints.every((k) => count(x[k]))) return false;
  if (x.income_replaced !== null && !amount(x.income_replaced)) return false;
  if (x.output !== null && !amount(x.output)) return false;
  const optional = ["stipends", "capital", "inputs", "household_sales", "household_sold"];
  if (optional.some((k) => x[k] !== undefined && !count(x[k]))) return false;
  const o = (k: string) => (x[k] as number | undefined) ?? 0;
  return x.cash_close === (x.cash_open as number) + o("capital") + (x.sales as number) + o("household_sales")
      - o("inputs") - (x.wages_paid as number) - (x.distributed as number) - (x.written_off as number) - o("stipends")
    && x.inventory_close === (x.inventory_open as number) + (x.titled as number) - (x.sold as number)
      - o("household_sold") - (x.worn as number) - (x.returned as number);
}

function validTransfers(x: unknown, source: number): boolean {
  if (!object(x) || !Array.isArray(x.money) || !Array.isArray(x.materials)) return false;
  return x.money.every((m) => object(m) && m.turn === source && MONEY.includes(m.kind as string)
      && account(m.payer) && account(m.payee) && count(m.amount) && count(m.applied) && count(m.residual)
      && (m.applied as number) + (m.residual as number) === m.amount)
    && x.materials.every((m) => object(m) && m.turn === source && MATERIAL.includes(m.kind as string)
      && account(m.source) && account(m.dest) && count(m.requested) && count(m.delivered)
      && (m.delivered as number) <= (m.requested as number));
}

/** Strict reader; null when absent, from another schema, misdated or not closing. */
export function workshopFinanceAt(snapshot: TurnSnapshot | null, regionCount: number): WorkshopFinanceRecord | null {
  const x = readLivelihoodRecord(snapshot, "workshop_payroll");
  if (!x || x.stage !== "L6a" || !MODES.includes(x.mode as string)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn || !object(x.units) || x.units.milli !== 1000
    || !Array.isArray(x.firms) || x.firms.length > 4 || !x.firms.every((f) => validFirm(f, regionCount))
    || !Array.isArray(x.closed) || x.closed.length > 8 || !x.closed.every((f) => validFirm(f, regionCount))
    || !object(x.counters) || !Object.values(x.counters).every(finite) || !object(x.parameters)) return null;
  if (x.receipts !== null && !(Array.isArray(x.receipts)
    && x.receipts.every((r) => validReceipt(r, regionCount, x.source_turn as number)))) return null;
  if (x.transfers !== null && !validTransfers(x.transfers, x.source_turn as number)) return null;
  return x as unknown as WorkshopFinanceRecord;
}

/** Milli-units (or milli-loads) as whole units. */
export const units = (milli: number) => milli / 1000;

export interface PayrollFunnel {
  operatingSiteTurns: number; offeredFirmTurns: number; customerFirmTurns: number; salesPaid: number;
  sales: number; wagesDue: number; wagesPaid: number; owedWrittenOff: number; owedLapsed: number;
  incomeReplaced: number; netCrewEffect: number; closedInsolvent: number;
}

/** Lifetime funnel from the scalar counters (units, not milli-units). */
export function payrollFunnel(record: WorkshopFinanceRecord): PayrollFunnel {
  const c = (key: string) => record.counters[key] ?? 0;
  const wagesPaid = units(c("wages_paid"));
  return {
    operatingSiteTurns: c("operating_site_turns"), offeredFirmTurns: c("offered_firm_turns"),
    customerFirmTurns: c("customer_firm_turns"), salesPaid: c("sales_paid"), sales: units(c("sales")),
    wagesDue: units(c("wages_due")), wagesPaid, owedWrittenOff: units(c("owed_written_off")),
    owedLapsed: units(c("owed_lapsed")), incomeReplaced: c("income_replaced"),
    netCrewEffect: wagesPaid - c("income_replaced"), closedInsolvent: c("closed_insolvent"),
  };
}
