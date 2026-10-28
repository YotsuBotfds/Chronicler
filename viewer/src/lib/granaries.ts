/** Public granary history, read only from per-turn records; never the final world. */
import type { GranarySnapshotRow, GrainReservesSnapshot, TurnSnapshot } from "../types";
import { factionColor } from "./colors";
import { buildSegments, type SeriesRow, type StripRow } from "./systems";

export function granaryAmounts(record: GrainReservesSnapshot, region: number | null = null) {
  const rows = record.granaries.filter((row) => region === null || row.region === region);
  const flows = record.flows.filter((flow) => region === null || flow.region === region);
  const amount = (kind: string) => flows.filter((flow) => flow.kind === kind).reduce((n, flow) => n + flow.amount, 0);
  return {
    stock: rows.reduce((n, row) => n + row.grain, 0),
    target: rows.reduce((n, row) => n + row.target, 0),
    bought: amount("bought"), released: amount("released"), spoiled: amount("spoiled"),
    seized: amount("seized"), abandoned: amount("abandoned"),
    paid: flows.reduce((n, flow) => n + flow.cost, 0),
    transit: flows.filter((flow) => flow.kind === "bought").reduce((n, flow) => n + flow.sent - flow.amount, 0),
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
