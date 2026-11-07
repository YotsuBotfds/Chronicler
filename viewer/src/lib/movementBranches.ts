import type { TurnSnapshot } from "../types";

export interface BranchRow {
  branch: number; movement: number; host: number; target: number; host_name: string; target_name: string;
  regions: number[]; members: number; payers: number[]; dues_milli: number; status: string; active_from: number | null;
}
export interface BranchRecord {
  schema_version: 1; stage: "D1c"; source_turn: number; mode: "funded" | "record_only" | "cost_only";
  frame: { turn: number; rows: BranchRow[]; new_identities_refused: number } | null;
}
const object = (x: unknown): x is Record<string, unknown> => !!x && typeof x === "object" && !Array.isArray(x);
const integer = (x: unknown, min = 0): x is number => typeof x === "number" && Number.isSafeInteger(x) && x >= min;
const modes = ["funded", "record_only", "cost_only"];
const statuses = ["record_only", "funded", "cost_only", "too_few", "poor", "capacity", "hostile", "quarantined", "ended", "empty", "payment_refused"];
function raw(snapshot: TurnSnapshot | null): unknown {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  return object(livelihoods) ? livelihoods.movement_branches : undefined;
}
export function movementBranchesOn(history: TurnSnapshot[]): boolean {
  return Array.isArray(history) && history.some((snapshot) => raw(snapshot) != null);
}
export function movementBranchesAt(snapshot: TurnSnapshot | null, regions: number, civs: number): {
  status: "absent" | "malformed" | "unobserved" | "recorded_zero" | "recorded"; record?: BranchRecord;
} {
  const x = raw(snapshot), bad = (): { status: "malformed" } => ({ status: "malformed" });
  if (x == null) return { status: "absent" };
  if (!object(x) || x.schema_version !== 1 || x.stage !== "D1c" || !integer(x.source_turn)
    || x.source_turn !== (snapshot?.turn ?? 0) - 1 || !modes.includes(x.mode as string)) return bad();
  if (x.frame === null) return { status: "unobserved", record: x as unknown as BranchRecord };
  if (!object(x.frame) || x.frame.turn !== x.source_turn || !integer(x.frame.new_identities_refused)
    || !Array.isArray(x.frame.rows) || x.frame.rows.length > 256) return bad();
  const ids = new Set<number>(), pairs = new Set<string>(), payers = new Set<number>();
  for (const value of x.frame.rows) {
    if (!object(value)) return bad();
    const r = value as unknown as BranchRow;
    if (!integer(r.branch, 1) || r.branch > 256 || !integer(r.movement, 1) || !integer(r.host) || r.host >= civs
      || !integer(r.target, -1) || r.target >= civs || !integer(r.members) || typeof r.host_name !== "string" || typeof r.target_name !== "string"
      || !statuses.includes(r.status) || !Array.isArray(r.regions) || !r.regions.every((v) => integer(v) && v < regions)
      || new Set(r.regions).size !== r.regions.length || !Array.isArray(r.payers) || r.payers.length > Math.min(32, r.members)
      || !r.payers.every((v) => integer(v, 1) && !payers.has(v)) || new Set(r.payers).size !== r.payers.length
      || !integer(r.dues_milli) || r.dues_milli !== r.payers.length * 10 || ids.has(r.branch) || pairs.has(`${r.movement}:${r.host}`)) return bad();
    if (r.status === "funded" || r.status === "cost_only") {
      if (r.payers.length < 3 || r.target === r.host || (r.status === "funded"
        ? x.mode !== "funded" || r.active_from !== x.source_turn + 1
        : x.mode !== "cost_only" || r.active_from !== null)) return bad();
    } else if (r.payers.length !== 0 || r.active_from !== null) return bad();
    ids.add(r.branch); pairs.add(`${r.movement}:${r.host}`); r.payers.forEach((v) => payers.add(v));
  }
  if (payers.size > 512) return bad();
  return { status: x.frame.rows.length ? "recorded" : "recorded_zero", record: x as unknown as BranchRecord };
}
