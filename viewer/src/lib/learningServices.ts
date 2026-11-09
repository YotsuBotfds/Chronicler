import type { SeatRecord, TurnSnapshot } from "../types";
import type { AcademyIdentity, AcademyInventory, AcademyProcurement, AcademySupplyLoss, AcademyTeaching, LearningServicesSnapshot } from "../learningServicesTypes";
import { isRecord as object, amount as num, safeCount as count } from "./recordGuards";

const nullable = (v: unknown, test: (x: unknown) => boolean) => v === null || test(v);
const bool = (v: unknown) => typeof v === "boolean";
const owner = (v: unknown) => v === -1 || count(v);
const identity = (v: unknown): v is AcademyIdentity => object(v) && count(v.seat_id) && count(v.region) && owner(v.founder)
  && count(v.founded_turn) && typeof v.seat_name === "string" && v.seat_name.length > 0;
const numbers = (row: Record<string, unknown>, keys: string[], nullableValues = true) => keys.every((key) => nullableValues ? nullable(row[key], num) : num(row[key]));
const counts = (row: Record<string, unknown>, keys: string[]) => keys.every((key) => nullable(row[key], count));
const booleans = (row: Record<string, unknown>, keys: string[]) => keys.every((key) => nullable(row[key], bool));
const same = (row: AcademyIdentity, id: number, seat: SeatRecord) => row.seat_id === id && row.region === seat.region
  && row.founder === seat.founder && row.founded_turn === seat.founded_turn && row.seat_name === seat.name;
const date = (v: unknown, through: number) => count(v) && v <= through;
const nullableDate = (v: unknown, through: number) => v === null || date(v, through);

type Reading = { frame: LearningServicesSnapshot; inventory: AcademyInventory | null; procurement: AcademyProcurement | null;
  teaching: AcademyTeaching | null; loss: AcademySupplyLoss | null };

/** Validate the exact snapshot and each selected-seat domain without borrowing other frames. */
export function learningServicesAt(snapshot: TurnSnapshot | null, id: number, seat: SeatRecord | null,
  regionCount: number, civCount: number, seatCount: number): Reading | null {
  const frame = snapshot?.scholarship?.learning_services;
  const through = snapshot ? snapshot.turn - 1 : -1;
  if (!frame || !count(through) || frame.schema_version !== 1 || frame.captured_turn !== snapshot!.turn
    || !bool(frame.enabled) || !bool(frame.active) || (frame.active && !frame.enabled)
    || !seat || seat.kind !== 0 || !count(id) || id >= seatCount || seat.founded_turn > through || !count(seat.region) || seat.region >= regionCount
    || !owner(seat.founder) || seat.founder >= civCount || typeof seat.name !== "string") return null;
  const matchedSeat = seat;
  function one<T extends AcademyIdentity>(rows: T[] | null, valid: (row: Record<string, unknown>) => boolean): T | null {
    if (!Array.isArray(rows)) return null;
    const found: T[] = [];
    for (const row of rows) {
      if (!identity(row) || !object(row) || row.seat_id >= seatCount || row.region >= regionCount
        || row.founder >= civCount || row.founded_turn > through || !valid(row)) return null;
      if (same(row, id, matchedSeat)) found.push(row);
    }
    return found.length === 1 ? found[0] : null;
  }
  const civ = (v: unknown) => owner(v) && (v as number) < civCount;
  const inventory = one(frame.inventories, (r) => numbers(r, ["held", "purchased_total", "used_total", "lost_total"])
    && bool(r.retired) && nullableDate(r.upkeep_source_turn, through) && nullable(r.upkeep_lord, civ)
    && counts(r, ["upkeep_due", "upkeep_amount_paid"]) && booleans(r, ["upkeep_satisfied"]));
  const receiptDate = (r: Record<string, unknown>) => date(r.source_turn, through)
    && (r.source_turn as number) >= (r.founded_turn as number)
    && nullableDate(r.upkeep_source_turn, r.source_turn as number)
    && (frame.active ? r.source_turn === through : true);
  const procurement = one(frame.procurement_receipts, (r) => receiptDate(r) && civ(r.lord)
    && nullableDate(r.upkeep_source_turn, through) && counts(r, ["upkeep_due", "upkeep_amount_paid", "scholar_upper_bound", "learner_upper_bound", "budget_before"])
    && booleans(r, ["upkeep_satisfied"]) && numbers(r, ["craft_price", "market_commitments", "held_before", "held_after"])
    && numbers(r, ["market_stock", "purchased", "paid"], false) && count(r.paid)
    && Array.isArray(r.shortfalls) && r.shortfalls.length <= 64
    && r.shortfalls.every((s) => typeof s === "string" && s.length <= 128));
  const teaching = one(frame.teaching_receipts, (r) => receiptDate(r) && civ(r.lord) && count(r.available_turn)
    && r.available_turn === (r.source_turn as number) + 1 && nullableDate(r.upkeep_source_turn, through) && nullable(r.upkeep_lord, civ)
    && counts(r, ["learner_upper_bound", "scholar_upper_bound", "upkeep_due", "upkeep_amount_paid", "native_dropped"])
    && booleans(r, ["upkeep_satisfied", "upkeep_applies"]) && numbers(r, ["held_before", "work_available", "work_reserved", "work_delivered", "learners_delivered", "crafts_used", "held_after"])
    && num(r.work_requested));
  // A loss can be reported while paused, including on the current tick.
  const loss = one(frame.supply_losses, (r) => date(r.source_turn, through) && (!frame.active || r.source_turn === through)
    && (r.source_turn as number) >= (r.founded_turn as number) && typeof r.reason === "string"
    && numbers(r, ["held_before", "lost", "held_after"]));
  return { frame, inventory, procurement, teaching, loss };
}
