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
    paid: flows.reduce((n, flow) => n + flow.cost, 0),
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
