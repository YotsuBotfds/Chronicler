/**
 * RL8: five strict readers (`repairProjectsAt`, `timberStockAt`, `remittancesAt`,
 * `foodAllocationAt`, `granaryStorageAt`) return null both when a record is absent
 * and when it is malformed. A reading puts the presence test in front of the
 * unchanged reader, so a panel can tell apart:
 *
 * - `disabled`: no snapshot of the run records the package (its switch is off);
 * - `absent`: the package is on in this run, but this snapshot has no record
 *   (or no livelihoods record at all): unknown, not zero;
 * - `malformed`: a record (or the livelihoods container) is present and was
 *   refused: nothing is shown from it;
 * - `unobserved`: a valid record whose turn was not observed (null frames):
 *   unknown, not zero;
 * - `recorded_zero`: a valid record saying nothing happened this turn;
 * - `recorded`: a valid record with something in it.
 *
 * The readers keep their contract (the recovery chain composes them the same
 * way, `recoveryChain.ts`); `granaries.ts` and its panel are pinned by a source
 * witness, so the granary storage reading is offered here without changing them.
 */
import type { Bundle, TurnSnapshot } from "../types";
import { foodAllocationAt, type FoodAllocationRecord } from "./foodAllocation";
import { granaryStorageAt } from "./granaries";
import { remittancesAt, type RemittancesRecord } from "./remittances";
import { repairProjectsAt, type RepairProjectsRecord } from "./repairProjects";
import { timberStockAt, type TimberStockRecord } from "./timberStock";

export type RecordState = "disabled" | "absent" | "malformed" | "unobserved" | "recorded_zero" | "recorded";

export type RecordReading<T> =
  | { state: "disabled" | "absent" | "malformed"; record: null; note: string }
  | { state: "unobserved" | "recorded_zero" | "recorded"; record: T; note: string };

export type GranaryStorageFrame = NonNullable<ReturnType<typeof granaryStorageAt>>;

interface RecordSpec<T> {
  key: string;
  label: string;
  flag: string;
  /** Whether the package lives in `snapshot.livelihoods` (versioned container). */
  livelihoods: boolean;
  carries: (snapshot: TurnSnapshot) => boolean;
  read: (snapshot: TurnSnapshot, regions: number, civs: number) => T | null;
  observed: (record: T) => boolean;
  empty: (record: T) => boolean;
  /** What "nothing happened" means for this record. */
  zero: string;
}

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);

function inLivelihoods(key: string) {
  return (snapshot: TurnSnapshot) => {
    const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
    return object(livelihoods) && livelihoods[key] !== undefined && livelihoods[key] !== null;
  };
}

const onInRun = new WeakMap<readonly TurnSnapshot[], Map<string, boolean>>();

/** Whether any snapshot of the run carries the package (cached per history). */
function recordedInRun<T>(history: readonly TurnSnapshot[], spec: RecordSpec<T>): boolean {
  let seen = onInRun.get(history);
  if (!seen) {
    seen = new Map();
    onInRun.set(history, seen);
  }
  let on = seen.get(spec.key);
  if (on === undefined) {
    on = history.some((snapshot) => snapshot !== null && typeof snapshot === "object" && spec.carries(snapshot));
    seen.set(spec.key, on);
  }
  return on;
}

/** One package at one snapshot: the presence test, then its own strict reader. */
export function readRecord<T>(spec: RecordSpec<T>, bundle: Bundle | null | undefined,
  snapshot: TurnSnapshot | null, currentTurn?: number): RecordReading<T> {
  const history = Array.isArray(bundle?.history) ? bundle!.history : [];
  const here = snapshot !== null && spec.carries(snapshot);
  const at = snapshot?.turn ?? currentTurn ?? "?";
  if (!here && !recordedInRun(history, spec)) {
    return { state: "disabled", record: null,
      note: `${spec.label}: off in this run (${spec.flag} is not recorded in any snapshot).` };
  }
  if (snapshot === null) {
    return { state: "absent", record: null, note: `${spec.label}: no snapshot at turn ${at}; unknown, not zero.` };
  }
  if (spec.livelihoods) {
    const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
    if (livelihoods === undefined || livelihoods === null) {
      return { state: "absent", record: null,
        note: `${spec.label}: no livelihoods record at snapshot ${at}; unknown, not zero.` };
    }
    if (!object(livelihoods) || livelihoods.schema_version !== 1) {
      return { state: "malformed", record: null,
        note: `${spec.label}: the livelihoods record at snapshot ${at} is unreadable (malformed or of an unknown version); nothing is shown from it.` };
    }
  }
  if (!here) {
    return { state: "absent", record: null,
      note: `${spec.label}: on in this run, but snapshot ${at} has no record; unknown, not zero.` };
  }
  const regions = bundle?.world_state?.regions?.length ?? 0;
  const civs = bundle?.world_state?.civilizations?.length ?? 0;
  const record = spec.read(snapshot, regions, civs);
  if (record === null) {
    return { state: "malformed", record: null,
      note: `${spec.label}: the record at snapshot ${at} was rejected as malformed (misdated, of another schema or inconsistent); nothing is shown from it.` };
  }
  if (!spec.observed(record)) {
    return { state: "unobserved", record,
      note: `${spec.label}: recorded at snapshot ${at}, but its turn was not observed; unknown, not zero.` };
  }
  if (spec.empty(record)) {
    return { state: "recorded_zero", record, note: `${spec.label}: recorded, nothing happened this turn (${spec.zero}).` };
  }
  return { state: "recorded", record, note: "" };
}

export const REPAIR_PROJECTS: RecordSpec<RepairProjectsRecord> = {
  key: "repair_projects", label: "Repair projects", flag: "--repair-projects", livelihoods: true,
  carries: inLivelihoods("repair_projects"), read: repairProjectsAt,
  observed: (r) => r.receipts !== null,
  empty: (r) => r.receipts !== null && r.receipts.length === 0 && r.projects.length === 0,
  zero: "no project open and no repair work",
};

const TIMBER_FLOWS = ["cleared", "extraction", "overdraft", "regrowth", "removed"] as const;

export const TIMBER_STOCK: RecordSpec<TimberStockRecord> = {
  key: "timber_stock", label: "Timber stock", flag: "--timber-stock", livelihoods: true,
  carries: inLivelihoods("timber_stock"), read: (s, regions) => timberStockAt(s, regions),
  observed: (r) => r.observed && r.totals !== null && r.regions !== null,
  empty: (r) => r.totals !== null && TIMBER_FLOWS.every((k) => r.totals![k] === 0),
  zero: "no timber cut, cleared, regrown or removed",
};

export const REMITTANCES: RecordSpec<RemittancesRecord> = {
  key: "remittances", label: "Remittances", flag: "--remittances", livelihoods: true,
  carries: inLivelihoods("remittances"), read: (s, regions) => remittancesAt(s, regions),
  observed: (r) => r.receipts !== null,
  empty: (r) => (r.receipts ?? []).length === 0 && (r.moves ?? []).length === 0 && (r.closures ?? []).length === 0
    && (r.unmet ?? []).length === 0,
  zero: "no remittance, migration or closure",
};

export const FOOD_ALLOCATION: RecordSpec<FoodAllocationRecord> = {
  key: "food_allocation", label: "Food allocation", flag: "--food-allocation", livelihoods: true,
  carries: inLivelihoods("food_allocation"), read: (s, regions) => foodAllocationAt(s, regions),
  observed: (r) => r.totals !== null && r.regions !== null,
  empty: (r) => r.regions !== null && r.regions.length === 0,
  zero: "no region was short of food",
};

export const GRANARY_STORAGE: RecordSpec<GranaryStorageFrame> = {
  key: "grain_storage", label: "Granary storage", flag: "--grain-storage", livelihoods: false,
  carries: (s) => s.grain_reserves?.storage != null, read: granaryStorageAt,
  observed: () => true,
  empty: (frame) => frame.receipts.every((row) => row.delivered === 0 && row.treasury_paid === 0 && row.timber_used === 0),
  zero: "no storage work delivered or paid",
};

export const readRepairProjects = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null, turn?: number) =>
  readRecord(REPAIR_PROJECTS, bundle, snapshot, turn);
export const readTimberStock = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null, turn?: number) =>
  readRecord(TIMBER_STOCK, bundle, snapshot, turn);
export const readRemittances = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null, turn?: number) =>
  readRecord(REMITTANCES, bundle, snapshot, turn);
export const readFoodAllocation = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null, turn?: number) =>
  readRecord(FOOD_ALLOCATION, bundle, snapshot, turn);
/** The granary storage state; its pinned panel (GranaryStorage.tsx) still renders its own note. */
export const readGranaryStorage = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null, turn?: number) =>
  readRecord(GRANARY_STORAGE, bundle, snapshot, turn);
