/**
 * Reader for `history[n].epidemics.quarantine_rules`, the record of
 * `--quarantine-mode` (connected-world C1; chronicler.quarantine_rules).
 *
 * Four states stay distinct: no epidemiology record at the snapshot
 * (unknown), an epidemiology record without the key (the legacy multiplier
 * rule, which closes no route), a malformed record, and a recorded mode
 * (whose counts may be a recorded zero). The reader is strict: it reports a
 * malformed record instead of guessing. Types live here, not in types.ts.
 *
 * C1b (`--quarantine-channels trade,migration`): a record whose channels
 * include "migration" carries refused migrants in each receipt (null: no
 * native migration receipt read that turn; 0: a recorded zero) and in the
 * totals; a trade-only record carries neither (migrants are not restricted).
 * Units: a receipt counts the persons refused that tick; the totals sum those
 * refusals over ticks (person-ticks: an agent refused on k ticks counts k
 * times) and count refusal spells separately (an agent refused on consecutive
 * ticks counts once per unbroken spell).
 */

export type QuarantineMode = "none" | "cost_only" | "closure";

export interface QuarantineClosureRecord {
  id: number;
  civ: string;
  target: string;
  opened_turn: number;
  last_renewed_turn: number;
  cause: string;
}

/** One refused move group of a migration closure (C1b). */
export interface MigrationRefusalRecord {
  closure: number;
  from: string;
  to: string;
  /** The movers' migration driver (native term name, or "unattributed"). */
  driver: string;
  persons: number;
}

export interface QuarantineReceiptRecord {
  turn: number;
  decided: [string, string][];
  continued: [string, string][];
  /** Pairs closed during the agent tick whose deliveries this receipt reads. */
  closed_last_tick: [string, string][];
  opened: number[];
  renewed: number[];
  lapsed: number[];
  enforcement: Record<string, number>;
  phase2_observed: boolean;
  routes_removed: [string, string][];
  forgone_income: Record<string, number>;
  /** Directed agent-merchant edges cut; null: no agent merchant graph that turn. */
  merchant_edges_removed: number | null;
  /** Deliveries of the last tick across a pair closed during it; null: none read that turn. */
  leaked_deliveries: number | null;
  leaked_quantity: number | null;
  /** C1b: persons refused at a closed border this turn; null: not observed (or no migration channel). */
  migrants_blocked: number | null;
  /** C1b: of them, fleeing war, famine or persecution (hunger-driven moves excluded). */
  migrants_blocked_flight: number | null;
  /** C1b: of them, hunger-driven (food opportunity, material need). */
  migrants_blocked_hunger: number | null;
  /** C1b: of them, not refused at the previous tick (a new refusal spell). */
  migrants_refused_new: number | null;
  migration_refusals: MigrationRefusalRecord[] | null;
}

export interface QuarantineTotalsRecord {
  receipts: number;
  closed_pair_turns: number;
  closures_opened: number;
  closures_lapsed: number;
  enforcement_paid: number;
  route_turns_removed: number;
  forgone_income: number;
  merchant_edges_removed: number;
  leaked_deliveries: number;
  leaked_quantity: number;
  /** C1b only (null without the migration channel): refusals summed over ticks (person-ticks). */
  migrants_blocked: number | null;
  migrants_blocked_flight: number | null;
  migrants_blocked_hunger: number | null;
  /** C1b: refusal spells (consecutive refusals of one agent count once). */
  migrants_refusal_spells: number | null;
}

export interface QuarantineRulesRecord {
  mode: QuarantineMode;
  channels: string[];
  exempt: string[];
  enforcement_cost: number;
  closures: QuarantineClosureRecord[];
  receipt: QuarantineReceiptRecord | null;
  totals: QuarantineTotalsRecord;
}

export type QuarantineReading =
  | { state: "unknown" }
  | { state: "legacy" }
  | { state: "malformed"; error: string }
  | { state: "recorded"; record: QuarantineRulesRecord };

export const QUARANTINE_MODE_LABEL: Record<QuarantineMode | "legacy", string> = {
  legacy: "Legacy multiplier",
  none: "No quarantine",
  cost_only: "Cost only (nothing closed)",
  closure: "Closure (trade closed)",
};

/** The mode label, naming migration when the record's closures also refuse it. */
export function quarantineModeLabel(record: QuarantineRulesRecord): string {
  return migrationClosed(record) ? "Closure (trade and migration closed)" : QUARANTINE_MODE_LABEL[record.mode];
}

/** Whether the record's closures refuse migration (C1b). */
export function migrationClosed(record: QuarantineRulesRecord): boolean {
  return record.mode === "closure" && record.channels.includes("migration");
}

export const MIGRATION_CLOSURE_NOTE = "Native migrations between the two polities of each closed pair are refused "
  + "at the border, either way; the movers stay home with their households (they are not sent elsewhere). Moves "
  + "made before the closure stay made, and refugees are refused like other migrants (counted apart).";

export const QUARANTINE_MODE_NOTE: Record<QuarantineMode | "legacy", string> = {
  legacy: "The legacy rule: a closed state's foreign import pressure is multiplied away (70–90%) and it pays "
    + "2 treasury a turn; no route or journey is closed.",
  none: "No quarantine decision, cost or restriction, and no import multiplier.",
  cost_only: "The same decisions and enforcement cost as a closure, with nothing closed and no import multiplier.",
  closure: "Trade routes and agent merchant border edges between each closing polity and the polities it closed "
    + "against are cut; exposure falls only through the contacts that no longer happen (no import multiplier).",
};

class ReadError extends Error {}

function fail(message: string): never {
  throw new ReadError(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function int(value: unknown, where: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) fail(`${where} must be an integer`);
  return value;
}

function num(value: unknown, where: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(`${where} must be a number`);
  return value;
}

function nullable<T>(value: unknown, read: (v: unknown, where: string) => T, where: string): T | null {
  return value === null || value === undefined ? null : read(value, where);
}

function text(value: unknown, where: string): string {
  if (typeof value !== "string") fail(`${where} must be a string`);
  return value;
}

function strings(value: unknown, where: string): string[] {
  if (!Array.isArray(value)) fail(`${where} must be a list`);
  return value.map((item, i) => text(item, `${where}[${i}]`));
}

function ints(value: unknown, where: string): number[] {
  if (!Array.isArray(value)) fail(`${where} must be a list`);
  return value.map((item, i) => int(item, `${where}[${i}]`));
}

function pairs(value: unknown, where: string): [string, string][] {
  if (!Array.isArray(value)) fail(`${where} must be a list`);
  return value.map((item, i) => {
    const pair = strings(item, `${where}[${i}]`);
    if (pair.length !== 2) fail(`${where}[${i}] must name two polities`);
    return [pair[0], pair[1]];
  });
}

function amounts(value: unknown, where: string): Record<string, number> {
  if (!isRecord(value)) fail(`${where} must be an object`);
  const out: Record<string, number> = {};
  for (const [key, item] of Object.entries(value)) out[key] = int(item, `${where}.${key}`);
  return out;
}

function readRefusals(value: unknown): MigrationRefusalRecord[] | null {
  if (value === null || value === undefined) return null;
  if (!Array.isArray(value)) fail("receipt.migration_refusals must be a list or null");
  return value.map((item, i) => {
    const where = `receipt.migration_refusals[${i}]`;
    if (!isRecord(item)) fail(`${where} must be an object`);
    return {
      closure: int(item.closure, `${where}.closure`),
      from: text(item.from, `${where}.from`),
      to: text(item.to, `${where}.to`),
      driver: text(item.driver, `${where}.driver`),
      persons: int(item.persons, `${where}.persons`),
    };
  });
}

function readReceipt(raw: unknown, migration: boolean): QuarantineReceiptRecord | null {
  if (raw === null) return null;
  if (!isRecord(raw)) fail("receipt must be an object or null");
  if (typeof raw.phase2_observed !== "boolean") fail("receipt.phase2_observed must be a boolean");
  if (migration && !("migrants_blocked" in raw)) fail("receipt.migrants_blocked is missing for the migration channel");
  const refusals = migration ? readRefusals(raw.migration_refusals) : null;
  const blocked = migration ? nullable(raw.migrants_blocked, int, "receipt.migrants_blocked") : null;
  if ((blocked === null) !== (refusals === null)) {
    fail("receipt.migrants_blocked and receipt.migration_refusals must both be recorded or both be null");
  }
  if (blocked !== null && blocked !== refusals!.reduce((sum, r) => sum + r.persons, 0)) {
    fail("receipt.migrants_blocked must equal the persons of its refusals");
  }
  return {
    turn: int(raw.turn, "receipt.turn"),
    decided: pairs(raw.decided, "receipt.decided"),
    continued: pairs(raw.continued ?? [], "receipt.continued"),
    closed_last_tick: pairs(raw.closed_last_tick ?? [], "receipt.closed_last_tick"),
    opened: ints(raw.opened, "receipt.opened"),
    renewed: ints(raw.renewed, "receipt.renewed"),
    lapsed: ints(raw.lapsed, "receipt.lapsed"),
    enforcement: amounts(raw.enforcement, "receipt.enforcement"),
    phase2_observed: raw.phase2_observed,
    routes_removed: pairs(raw.routes_removed, "receipt.routes_removed"),
    forgone_income: amounts(raw.forgone_income, "receipt.forgone_income"),
    merchant_edges_removed: nullable(raw.merchant_edges_removed, int, "receipt.merchant_edges_removed"),
    leaked_deliveries: nullable(raw.leaked_deliveries, int, "receipt.leaked_deliveries"),
    leaked_quantity: nullable(raw.leaked_quantity, num, "receipt.leaked_quantity"),
    migrants_blocked: blocked,
    migrants_blocked_flight: migration
      ? nullable(raw.migrants_blocked_flight, int, "receipt.migrants_blocked_flight") : null,
    migrants_blocked_hunger: migration
      ? nullable(raw.migrants_blocked_hunger, int, "receipt.migrants_blocked_hunger") : null,
    migrants_refused_new: migration
      ? nullable(raw.migrants_refused_new, int, "receipt.migrants_refused_new") : null,
    migration_refusals: refusals,
  };
}

const TOTALS: (keyof QuarantineTotalsRecord)[] = [
  "receipts", "closed_pair_turns", "closures_opened", "closures_lapsed", "enforcement_paid",
  "route_turns_removed", "forgone_income", "merchant_edges_removed", "leaked_deliveries",
];

function readTotals(raw: unknown, migration: boolean): QuarantineTotalsRecord {
  if (!isRecord(raw)) fail("totals must be an object");
  const out = { leaked_quantity: num(raw.leaked_quantity ?? 0, "totals.leaked_quantity") } as QuarantineTotalsRecord;
  for (const key of TOTALS) out[key] = int(raw[key], `totals.${key}`);
  out.migrants_blocked = migration ? int(raw.migrants_blocked, "totals.migrants_blocked") : null;
  out.migrants_blocked_flight = migration ? int(raw.migrants_blocked_flight, "totals.migrants_blocked_flight") : null;
  out.migrants_blocked_hunger = migration ? int(raw.migrants_blocked_hunger, "totals.migrants_blocked_hunger") : null;
  out.migrants_refusal_spells = migration
    ? int(raw.migrants_refusal_spells, "totals.migrants_refusal_spells") : null;
  return out;
}

/** Read `epidemics.quarantine_rules` from a snapshot's `epidemics` record (`undefined`: none). */
export function readQuarantineRules(epidemics: unknown): QuarantineReading {
  if (epidemics === undefined || epidemics === null) return { state: "unknown" };
  if (!isRecord(epidemics)) return { state: "malformed", error: "epidemics must be an object" };
  if (!("quarantine_rules" in epidemics)) return { state: "legacy" };
  try {
    const raw = epidemics.quarantine_rules;
    if (!isRecord(raw)) fail("quarantine_rules must be an object");
    if (raw.schema_version !== 1) fail(`unsupported schema_version ${String(raw.schema_version)}`);
    if (raw.mode !== "none" && raw.mode !== "cost_only" && raw.mode !== "closure") {
      fail(`unknown mode ${String(raw.mode)}`);
    }
    if (!Array.isArray(raw.closures)) fail("closures must be a list");
    const closures = raw.closures.map((item, i) => {
      if (!isRecord(item)) fail(`closures[${i}] must be an object`);
      return {
        id: int(item.id, `closures[${i}].id`),
        civ: text(item.civ, `closures[${i}].civ`),
        target: text(item.target, `closures[${i}].target`),
        opened_turn: int(item.opened_turn, `closures[${i}].opened_turn`),
        last_renewed_turn: int(item.last_renewed_turn, `closures[${i}].last_renewed_turn`),
        cause: text(item.cause, `closures[${i}].cause`),
      };
    });
    const channels = strings(raw.channels, "channels");
    const migration = raw.mode === "closure" && channels.includes("migration");
    return {
      state: "recorded",
      record: {
        mode: raw.mode,
        channels,
        exempt: strings(raw.exempt, "exempt"),
        enforcement_cost: int(raw.enforcement_cost, "enforcement_cost"),
        closures,
        receipt: readReceipt(raw.receipt ?? null, migration),
        totals: readTotals(raw.totals, migration),
      },
    };
  } catch (error) {
    if (error instanceof ReadError) return { state: "malformed", error: error.message };
    throw error;
  }
}

/** Sum of a per-polity amount map (0 for an empty, recorded map). */
export function totalOf(amountsByCiv: Record<string, number>): number {
  return Object.values(amountsByCiv).reduce((sum, value) => sum + value, 0);
}

export const EXEMPT_LABEL: Record<string, string> = {
  relief_grain: "relief grain shipments and convoys",
  armies: "armies",
  hostages: "hostages",
  migrants: "migrants",
  pilgrims: "pilgrims",
};
