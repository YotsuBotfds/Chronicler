/** Public granary history, read only from per-turn records; never the final world. */
import type { GranarySnapshotRow, GrainReservesSnapshot, TurnSnapshot } from "../types";
import { factionColor } from "./colors";
import { buildSegments, type SeriesRow, type StripRow } from "./systems";

export function granaryAmounts(record: GrainReservesSnapshot, region: number | null = null) {
  const rows = record.granaries.filter((row) => region === null || row.region === region);
  const flows = record.flows.filter((flow) => region === null || flow.region === region);
  const amount = (kind: string) => flows.filter((flow) => flow.kind === kind).reduce((n, flow) => n + flow.amount, 0);
  // Stored grain is recorded independently of the demand samples used for a
  // target. A partial sum would look like a complete target in tiles/charts.
  const targetKnown = (region === null || rows.length > 0)
    && rows.every((row) => row.observed > 0 && Number.isFinite(row.target));
  return {
    stock: rows.reduce((n, row) => n + row.grain, 0),
    target: targetKnown ? rows.reduce((n, row) => n + row.target, 0) : null,
    bought: amount("bought"), released: amount("released"), spoiled: amount("spoiled"),
    seized: amount("seized"), abandoned: amount("abandoned"),
    storageReturned: amount("storage_returned"),
    paid: flows.filter((flow) => flow.kind === "bought" || flow.kind === "dispatched").reduce((n, flow) => n + flow.cost, 0),
    transit: flows.filter((flow) => flow.kind === "bought" || flow.kind === "dispatched")
      .reduce((n, flow) => n + flow.sent - flow.amount, 0),
  };
}

/** No future records, and unknown older rows stay gaps rather than zero stock. */
export function granarySeries(history: TurnSnapshot[], turn: number, region: number | null): SeriesRow[] {
  return history.filter((snapshot) => snapshot.turn <= turn).map((snapshot) => {
    const record = snapshot.grain_reserves;
    const known = record && (region === null || record.granaries.some((row) => row.region === region));
    const amounts = known ? granaryAmounts(record, region) : null;
    return { turn: snapshot.turn, Stocks: amounts?.stock ?? null, Targets: amounts?.target ?? null,
      Bought: amounts?.bought ?? null, Released: amounts?.released ?? null, Spoiled: amounts?.spoiled ?? null };
  });
}

export function granaryKeeper(row: GranarySnapshotRow): string {
  return row.owner_name ?? (row.owner < 0 ? "No keeper" : `Civilization ${row.owner}`);
}

/** The recorded keeper can differ from territorial control until Phase 2 settles ownership. */
export function granaryOwnerRows(history: TurnSnapshot[], turn: number, region: number | null): StripRow[] {
  const prefix = history.filter((snapshot) => snapshot.turn <= turn);
  const names = new Map<number, string>();
  for (const snapshot of prefix) {
    for (const row of snapshot.grain_reserves?.granaries ?? []) {
      if (region === null || row.region === region) names.set(row.region, row.region_name);
    }
  }
  return [...names].map(([id, name]) => {
    const states = prefix.map((snapshot) => snapshot.grain_reserves?.granaries.find((row) => row.region === id));
    return { id: String(id), label: name, segments: buildSegments(prefix.map((snapshot) => snapshot.turn),
      states.map((row) => row ? String(row.owner) : null)).map((segment) => {
      const row = states[segment.from]!;
      const keeper = granaryKeeper(row);
      return { start: segment.start, end: segment.end, color: row.owner < 0 ? "#7d8a96" : factionColor(keeper),
        label: `${name}: ${keeper}, snapshots ${segment.start}-${segment.end - 1}`, text: keeper };
    }) };
  });
}

/** Only completed, matching shipment observations can describe cargo at a snapshot. */
export function granaryShipmentsAt(snapshot: TurnSnapshot | null) {
  const record = snapshot?.grain_reserves;
  const frame = record?.shipments;
  const nonnegative = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0;
  const turn = (value: unknown): value is number => nonnegative(value) && Number.isInteger(value);
  if (!frame || record!.source_turn !== snapshot!.turn - 1 || frame.source_turn !== record!.source_turn
    || frame.schema_version !== 1 || typeof frame.accept_orders !== "boolean"
    || !turn(frame.pending_count) || !nonnegative(frame.pending_net) || !Array.isArray(frame.transitions)
    || !frame.transitions.every((row) => row && [row.source_name, row.dest_name, row.buyer_name, row.seller_name, row.id]
      .every((value) => typeof value === "string" && value.length > 0)
      && row.turn === frame.source_turn && turn(row.dispatch_turn) && row.dispatch_turn <= frame.source_turn
      && row.due_turn === row.dispatch_turn + 1
      && (row.operation === "dispatched" ? row.turn === row.dispatch_turn
        : row.operation === "arrived" && row.turn >= row.due_turn)
      && [row.sent, row.net, row.loss, row.paid].every(nonnegative) && row.net > 0 && row.sent >= row.net
      && Number.isInteger(row.paid) && row.paid > 0)) return null;
  const dispatched = frame.transitions.filter((row) => row.operation === "dispatched").reduce((sum, row) => sum + row.net, 0);
  const arrived = frame.transitions.filter((row) => row.operation === "arrived").reduce((sum, row) => sum + row.net, 0);
  return Number.isFinite(dispatched) && Number.isFinite(arrived) ? { ...frame, dispatched, arrived } : null;
}

/** Storage is independently source-dated; do not substitute an adjacent or final frame. */
export function granaryStorageAt(snapshot: TurnSnapshot | null, regionCount: number, civCount: number) {
  const record = snapshot?.grain_reserves;
  const frame = record?.storage;
  const nonnegative = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
  const owner = (v: unknown) => typeof v === "number" && Number.isInteger(v) && v >= -1 && v < civCount;
  const policy = (v: unknown) => v === "neglect" || v === "maintain" || v === "expand";
  const fields = (obj: object, keys: string[]) => keys.every((key) => nonnegative((obj as Record<string, unknown>)[key]));
  if (!frame || !Number.isInteger(record!.source_turn) || record!.source_turn < 0
    || record!.source_turn !== snapshot!.turn - 1 || frame.schema_version !== 1
    || frame.receipt_turn !== record!.source_turn || !Array.isArray(frame.assets) || frame.assets.length !== regionCount
    || !Array.isArray(frame.policies) || frame.policies.length !== regionCount || !Array.isArray(frame.receipts)
    || !frame.assets.every((a) => a === null || (a && owner(a.owner) && fields(a, ["capacity", "condition", "repair_progress", "expansion_progress"]) && a.condition <= 1))
    || !frame.policies.every((p) => p && policy(p.policy) && nonnegative(p.work_budget) && p.work_budget <= 4)) return null;
  const seen = new Set<number>();
  for (const row of frame.receipts) {
    if (!row || row.turn !== frame.receipt_turn || !Number.isInteger(row.region) || row.region < 0 || row.region >= regionCount
      || seen.has(row.region) || !owner(row.owner) || !policy(row.policy)
      || !fields(row, ["requested", "delivered", "timber_reserved", "timber_used", "timber_returned", "treasury_paid", "condition_before", "condition_after", "capacity_before", "capacity_after", "repair_progress", "expansion_progress", "capacity_returned"])
      || !Number.isInteger(row.treasury_paid) || row.delivered > row.requested || row.condition_before > 1 || row.condition_after > 1
      || !(row.target_requested === null || nonnegative(row.target_requested)) || !(row.target_feasible === null || nonnegative(row.target_feasible))) return null;
    seen.add(row.region);
  }
  return frame;
}
