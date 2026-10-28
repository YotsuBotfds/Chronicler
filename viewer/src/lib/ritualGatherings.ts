import type { RitualGatheringOutcome, TurnSnapshot } from "../types";
import { observationAt } from "./observedSystems";
import type { StripRow } from "./systems";

export interface ObservedGathering extends RitualGatheringOutcome {
  snapshot_turn: number;
}

/** Current-turn receipts only: stale repeated outcomes cannot become fresh gatherings. */
export function gatheringHistory(history: TurnSnapshot[], through: number): ObservedGathering[] {
  const rows = new Map<string, ObservedGathering>();
  for (const snapshot of history) {
    if (snapshot.turn > through) continue;
    const record = observationAt(snapshot, "ritual_gatherings");
    for (const outcome of record?.outcomes ?? []) {
      if (outcome.turn !== record!.source_turn) continue;
      const key = `${outcome.gathering_id}@${outcome.turn}`;
      if (!rows.has(key)) rows.set(key, { ...outcome, snapshot_turn: snapshot.turn });
    }
  }
  return [...rows.values()].sort((a, b) => b.turn - a.turn || a.region - b.region);
}

export function gatheringRows(history: TurnSnapshot[], through: number): StripRow[] {
  const grouped = new Map<string, ObservedGathering[]>();
  for (const row of gatheringHistory(history, through).reverse()) {
    const rows = grouped.get(row.gathering_id) ?? [];
    rows.push(row);
    grouped.set(row.gathering_id, rows);
  }
  return [...grouped].map(([id, rows]) => ({ id, label: rows[0].region_name,
    segments: rows.map((row) => ({ start: row.snapshot_turn, end: row.snapshot_turn + 1,
      color: row.status === "held" ? "#5aa88f" : "#7d8a96", text: row.status,
      label: `${row.region_name}: ${row.status}, simulation turn ${row.turn} (snapshot ${row.snapshot_turn})` })) }));
}
