import { isRecord as object, finite, count as integer } from "./recordGuards";
import type { FoodAccountingSnapshot, TurnSnapshot } from "../types";

const nullableNumber = (x: unknown) => x === null || finite(x);
const nativeFields = ["opening", "produced", "transport_net", "craft_input", "clamp_correction", "pre_consumption", "consumed", "storage_loss", "cap_overflow", "closing", "demand", "sufficiency", "balance_residual", "balance_tolerance"];
const publicFields = ["released", "spoiled", "abandoned", "captured", "after_open"];

/** Reject malformed and future records; never borrow observations from other snapshots. */
export function foodAccountingAt(snapshot: TurnSnapshot | null, regionCount: number, civCount: number): FoodAccountingSnapshot | null {
  const x: unknown = snapshot?.food_accounting;
  if (!object(x) || x.schema_version !== 1 || typeof x.mode !== "string" || !integer(x.source_turn)
    || !integer(x.completed_turn) || x.completed_turn !== x.source_turn + 1 || x.completed_turn !== snapshot?.turn
    || x.timing !== "phase2" || x.units !== "model_food_goods"
    || !["physical_delivery", "abstract_allocation", "none"].includes(String(x.transport))
    || !Array.isArray(x.regions) || !Array.isArray(x.procurement)) return null;
  const regions = new Set<number>();
  for (const row of x.regions) {
    if (!object(row) || !integer(row.region_id) || row.region_id >= regionCount || regions.has(row.region_id)
      || !(row.native_count === null || integer(row.native_count)) || (!finite(row.model_population) || row.model_population < 0)
      || !nullableNumber(row.sufficiency_after_relief)) return null;
    regions.add(row.region_id);
    if (row.native !== null && (!object(row.native) || !nativeFields.every((key) => finite((row.native as Record<string, unknown>)[key])))) return null;
    if (row.public !== null && (!object(row.public) || !(row.public.owner_id === -1 || integer(row.public.owner_id)) || row.public.owner_id >= civCount
      || !nullableNumber(row.public.opening) || !nullableNumber(row.public.balance_residual)
      || !publicFields.every((key) => finite((row.public as Record<string, unknown>)[key])))) return null;
  }
  const civs = new Set<number>();
  for (const row of x.procurement) {
    if (!object(row) || !integer(row.civilization_id) || row.civilization_id >= civCount || civs.has(row.civilization_id)
      || !integer(row.budget_initial) || !integer(row.budget_remaining) || !integer(row.spent)) return null;
    civs.add(row.civilization_id);
  }
  return x as unknown as FoodAccountingSnapshot;
}
