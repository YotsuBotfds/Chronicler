/** D4 source-dated physical food transfers and liabilities; arrears are not money. */
import { isRecord as object, finite, safeCount as count } from "./recordGuards";
import type { TurnSnapshot } from "../types";
export interface RequisitionEvent {
  source_turn: number; kind: "requisition" | "cargo_seizure" | "refill" | "forage" | "initial" | "consumption";
  region?: number; army?: string; owner?: number; shipment?: number; payer?: number | null;
  goods?: string; package?: string; cause?: string;
  removed_milli?: number; destroyed_milli?: number; quantity_milli?: number; acquisition_value_milli?: number;
  allocations?: { army: string; rations: number }[]; credited_rations?: number;
  consumed_rations?: number; demanded_rations?: number; adequacy?: number;
}
export interface RestitutionClaim { id: number; turn: number; payer: number; owner: number; region: number; due_milli: number; paid_milli: number; source: string; status: "open" | "paid" | "owner_dead" | "pool_reset" }
export interface WarRequisitionRecord {
  schema_version: 1; stage: "D4"; mode: "transfer" | "cost_only"; enabled: boolean; source_turn: number | null;
  frame: null | { turn: number; events: RequisitionEvent[]; events_dropped: number; claims: RestitutionClaim[];
    claims_dropped: number; claims_open: number; claims_due_milli: number };
  counters: Record<string, number>;
}
export function warRequisitionAt(snapshot: TurnSnapshot | null, regions: number, civs: number):
  { status: "absent" | "disabled" | "malformed" | "unobserved" | "observed"; record: WarRequisitionRecord | null } {
  const lh = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  if (lh == null || (object(lh) && lh.war_requisition == null)) return { status: "absent", record: null };
  const bad = () => ({ status: "malformed" as const, record: null });
  if (!object(lh) || lh.schema_version !== 1) return bad();
  const x = lh.war_requisition, region = (r: unknown) => count(r) && r < regions, civ = (r: unknown) => count(r) && r < civs;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "D4" || !["transfer", "cost_only"].includes(x.mode as string) || typeof x.enabled !== "boolean"
    || (x.source_turn !== null && (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn))
    || !object(x.counters) || !Object.values(x.counters).every(count)) return bad();
  if (x.frame === null) return { status: x.enabled ? "unobserved" : "disabled", record: x as unknown as WarRequisitionRecord };
  const f = x.frame;
  if (!object(f) || f.turn !== x.source_turn || !count(x.source_turn) || !Array.isArray(f.events) || f.events.length > 256 || !count(f.events_dropped)
    || !Array.isArray(f.claims) || f.claims.length > 256 || !count(f.claims_dropped) || !count(f.claims_open) || !count(f.claims_due_milli)) return bad();
  const kinds = ["requisition", "cargo_seizure", "refill", "forage", "initial", "consumption"];
  for (const e of f.events) {
    if (!object(e) || e.source_turn !== x.source_turn || !kinds.includes(e.kind as string) || (e.region !== undefined && !region(e.region))
      || (e.payer != null && !civ(e.payer)) || (e.army !== undefined && (typeof e.army !== "string" || !e.army))
      || (e.owner !== undefined && !count(e.owner)) || (e.shipment !== undefined && !count(e.shipment))) return bad();
    for (const [k, v] of Object.entries(e)) if ((k.endsWith("_milli") || k.endsWith("_rations")) && !count(v)) return bad();
    if (e.allocations !== undefined && (!Array.isArray(e.allocations) || !e.allocations.every((a) => object(a) && typeof a.army === "string" && !!a.army && count(a.rations)))) return bad();
    if (e.kind === "requisition" || (e.kind === "cargo_seizure" && e.package !== "timber_orders")) {
      if (!count(e.removed_milli) || !count(e.destroyed_milli) || !Array.isArray(e.allocations)
        || e.removed_milli !== e.destroyed_milli + e.allocations.reduce((s, a) => s + (a as { rations: number }).rations * 500, 0)) return bad();
    }
    if (e.kind === "consumption" && (!count(e.consumed_rations) || !count(e.demanded_rations) || e.consumed_rations > e.demanded_rations
      || !finite(e.adequacy) || Math.abs(e.adequacy - (e.demanded_rations ? e.consumed_rations / e.demanded_rations : 0)) > 1e-8)) return bad();
  }
  const ids = new Set<number>();
  for (const c of f.claims) {
    if (!object(c) || !count(c.id) || ids.has(c.id) || !count(c.turn) || c.turn > x.source_turn || !civ(c.payer) || !count(c.owner) || !region(c.region)
      || !count(c.due_milli) || !count(c.paid_milli) || c.paid_milli > c.due_milli || typeof c.source !== "string"
      || !["open", "paid", "owner_dead", "pool_reset"].includes(c.status as string) || (c.status === "paid" && c.paid_milli !== c.due_milli)) return bad();
    ids.add(c.id);
  }
  if (f.claims_dropped === 0) {
    const open = (f.claims as unknown as RestitutionClaim[]).filter((c) => c.status === "open");
    if (f.claims_open !== open.length || f.claims_due_milli !== open.reduce((s, c) => s + c.due_milli - c.paid_milli, 0)) return bad();
  }
  return { status: x.enabled ? "observed" : "disabled", record: x as unknown as WarRequisitionRecord };
}
