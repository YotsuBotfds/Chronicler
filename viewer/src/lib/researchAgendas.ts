import type { ResearchCapacityKey, ScientificClaimsSnapshot, ScientificResearchAgendas } from "../expansionTypes";

export const RESEARCH_CAPACITIES: Record<ResearchCapacityKey, { label: string; limit: number }> = {
  topics: { label: "Canonical topics", limit: 20 }, trials: { label: "Paid trials", limit: 40 },
  proposals: { label: "Question receipts", limit: 400 }, receipts: { label: "Evidence receipts", limit: 800 },
  messages: { label: "Pending messages", limit: 1200 }, cycles: { label: "Agenda cycles", limit: 10 },
  seats: { label: "Lifetime enrolled seats", limit: 20 },
};
type ObjectRow = Record<string, unknown>;
const object = (v: unknown): v is ObjectRow => v !== null && typeof v === "object" && !Array.isArray(v);
const integer = (v: unknown, min = 0): v is number => Number.isSafeInteger(v) && (v as number) >= min;
const text = (v: unknown): v is string => typeof v === "string" && v.length <= 4096;
const actual = (v: unknown, source: number): v is number => integer(v) && v <= source;
const optionalActual = (v: unknown, source: number) => v === null || actual(v, source);
const ids = (v: unknown, max: number, high = Number.MAX_SAFE_INTEGER): v is number[] => Array.isArray(v)
  && v.length <= max && v.every((id) => integer(id) && id <= high) && new Set(v).size === v.length;
const keys = (v: ObjectRow, expected: string[]) => Object.keys(v).length === expected.length && expected.every((key) => Object.hasOwn(v, key));
const META_KEYS = ["schema_version", "rule", "enabled", "enabled_turn", "current_cycle_id", "next_open_turn",
  "opening_interval", "funding_window", "original_window", "effort_started_turn", "effort_cadence", "paid_use_seasons",
  "origin_cursor", "blocked_reason", "blocked_turn", "capacity", "archive", "cycles"];
const CYCLE_KEYS = ["id", "legacy_adopted", "opening_roster_complete", "opened_turn", "origin_seat", "participants",
  "claims", "trials", "announcement_event_id", "closed_turn", "close_reason", "unfunded_originals", "unfunded_replications",
  "slot_reasons", "original_deadline", "funding_deadline", "next_open_not_before", "opening_roster_scope"];

export type ResearchAgendaObservation = { status: "legacy" } | { status: "unknown" }
  | { status: "known"; record: ScientificResearchAgendas };

/** Bounded v1 metadata only; retained IDs never stand in for missing receipt bodies. */
export function researchAgendasAt(science: ScientificClaimsSnapshot): ResearchAgendaObservation {
  if (!Object.hasOwn(science, "research_agendas")) return { status: "legacy" };
  const invalid: ResearchAgendaObservation = { status: "unknown" };
  const raw: unknown = science.research_agendas, source = science.source_turn;
  if (!integer(source) || !object(raw) || !keys(raw, META_KEYS) || raw.schema_version !== 1 || raw.rule !== "finite-retained-v1"
    || typeof raw.enabled !== "boolean" || !actual(raw.enabled_turn, source) || !integer(raw.next_open_turn)
    || !integer(raw.origin_cursor, -1) || !optionalActual(raw.effort_started_turn, source)
    || !optionalActual(raw.blocked_turn, source) || !text(raw.blocked_reason)
    || Boolean(raw.blocked_reason) !== (raw.blocked_turn !== null)
    || raw.opening_interval !== 25 || raw.funding_window !== 24 || raw.original_window !== 12 || raw.effort_cadence !== 6
    || !ids(raw.paid_use_seasons, 2, 3) || !Array.isArray(raw.cycles) || raw.cycles.length > 10) return invalid;
  const seasons = raw.effort_started_turn === null ? [] : [...new Set([
    Math.floor((raw.effort_started_turn as number) % 12 / 3), Math.floor(((raw.effort_started_turn as number) + 6) % 12 / 3),
  ])].sort();
  if (JSON.stringify(raw.paid_use_seasons) !== JSON.stringify(seasons)) return invalid;
  const open: number[] = [], trialIds: number[] = [];
  for (const [index, cycle] of raw.cycles.entries()) {
    if (!object(cycle) || !keys(cycle, CYCLE_KEYS) || cycle.id !== index || typeof cycle.legacy_adopted !== "boolean"
      || typeof cycle.opening_roster_complete !== "boolean" || !optionalActual(cycle.opened_turn, source)
      || !optionalActual(cycle.closed_turn, source) || !integer(cycle.origin_seat) || !ids(cycle.participants, 20)
      || !ids(cycle.claims, 2, 19) || cycle.claims.length !== 2 || !ids(cycle.trials, 4, 39)
      || !ids(cycle.unfunded_originals, 2, 19) || !ids(cycle.unfunded_replications, 2, 19)
      || !text(cycle.announcement_event_id) || !text(cycle.close_reason) || !object(cycle.slot_reasons)) return invalid;
    const claims = cycle.claims;
    if ([...cycle.unfunded_originals, ...cycle.unfunded_replications].some((id) => !claims.includes(id))) return invalid;
    const allowed = new Set(cycle.claims.flatMap((id) => [`original:${id}`, `replication:${id}`]));
    if (Object.entries(cycle.slot_reasons).some(([key, value]) => !allowed.has(key) || !text(value) || value.length === 0)
      || (cycle.closed_turn !== null && cycle.opened_turn !== null && (cycle.closed_turn as number) < (cycle.opened_turn as number))
      || (cycle.closed_turn === null ? Boolean(cycle.close_reason) : !cycle.close_reason)) return invalid;
    if (cycle.legacy_adopted) {
      if (index !== 0 || cycle.opening_roster_complete || (cycle.opened_turn !== null && (cycle.opened_turn as number) > raw.enabled_turn)
        || cycle.closed_turn !== raw.enabled_turn || cycle.opening_roster_scope !== "observed_at_legacy_activation"
        || [cycle.original_deadline, cycle.funding_deadline, cycle.next_open_not_before].some((date) => date !== null)) return invalid;
    } else {
      if (!cycle.opening_roster_complete || !integer(cycle.opened_turn) || cycle.opened_turn < raw.enabled_turn
        || !cycle.participants.includes(cycle.origin_seat) || cycle.opening_roster_scope !== "frozen_at_actual_opening"
        || !cycle.announcement_event_id || cycle.original_deadline !== cycle.opened_turn + 11
        || cycle.funding_deadline !== cycle.opened_turn + 23 || cycle.next_open_not_before !== cycle.opened_turn + 25) return invalid;
      if (cycle.closed_turn === null) {
        if (source > cycle.opened_turn + 23) return invalid;
        open.push(index);
      }
    }
    trialIds.push(...cycle.trials);
  }
  if (raw.current_cycle_id !== null && (!integer(raw.current_cycle_id) || raw.current_cycle_id > 9)) return invalid;
  if (open.length > 1 || JSON.stringify(open) !== JSON.stringify(raw.current_cycle_id === null ? [] : [raw.current_cycle_id])
    || (!raw.enabled && raw.current_cycle_id !== null)) return invalid;
  const capacity = raw.capacity, archive = raw.archive;
  if (!object(capacity) || !keys(capacity, Object.keys(RESEARCH_CAPACITIES)) || !object(archive)
    || !keys(archive, ["retained_topics", "retained_trials", "retained_proposals", "retained_receipts", "raw_records_retained",
      "trial_details_scope", "historical_export_completeness"]) || archive.raw_records_retained !== true
    || archive.trial_details_scope !== "resolved_this_source_turn_only" || archive.historical_export_completeness !== "not_inferred") return invalid;
  for (const [name, spec] of Object.entries(RESEARCH_CAPACITIES)) {
    const row = capacity[name];
    if (!object(row) || !keys(row, ["used", "reserved", "limit"]) || !integer(row.used) || !integer(row.reserved)
      || row.limit !== spec.limit || row.used + row.reserved > spec.limit) return invalid;
  }
  const data = raw as unknown as ScientificResearchAgendas;
  for (const [index, cycle] of data.cycles.entries()) {
    const previous = data.cycles[index - 1];
    if (previous && (cycle.opened_turn === null || previous.closed_turn === null || previous.closed_turn > cycle.opened_turn
      || cycle.opened_turn < (previous.legacy_adopted ? data.enabled_turn : previous.opened_turn!) + 25)) return invalid;
  }
  const latest = data.cycles.at(-1);
  const earliest = latest ? (latest.legacy_adopted ? data.enabled_turn : latest.opened_turn!) + 25 : data.enabled_turn;
  if (data.next_open_turn < earliest || data.origin_cursor !== (latest?.origin_seat ?? -1)) return invalid;
  const counts = { topics: science.claims, trials: science.trials, receipts: science.evidence_receipts,
    messages: science.pending_messages, cycles: data.cycles.length, seats: science.seats };
  if (Object.entries(counts).some(([name, count]) => !integer(count) || data.capacity[name as ResearchCapacityKey].used !== count)
    || (["topics", "cycles", "seats"] as const).some((name) => data.capacity[name].reserved !== 0)
    || (["topics", "trials", "proposals", "receipts"] as const).some((name) => data.archive[`retained_${name}`] !== data.capacity[name].used)
    || trialIds.length !== science.trials || trialIds.sort((a, b) => a - b).some((id, index) => id !== index)) return invalid;
  if (!Array.isArray(science.propositions) || science.propositions.length !== science.claims
    || science.propositions.some((claim, index) => !object(claim) || claim.id !== index || !actual(claim.proposed_turn, source)
      || !["irrigation", "masonry"].includes(claim.recipe) || claim.metric !== "grain_output" || claim.comparator !== 0
      || claim.intervention !== 1 || claim.horizon !== 1 || claim.threshold !== .02
      || !object(claim.context) || !keys(claim.context, ["crop", "soil_band", "water_band", "season", "climate_phase", "crew", "protocol"])
      || claim.context.crop !== "grain" || claim.context.crew !== 4 || claim.context.protocol !== "fixed-crew-grain-v1"
      || !text(claim.context.climate_phase) || [claim.context.soil_band, claim.context.water_band, claim.context.season].some((v) => !integer(v) || v > 3))
    || data.cycles.some((cycle) => cycle.claims.some((id) => !science.propositions[id]))) return invalid;
  const contextKey = (claim: ScientificClaimsSnapshot["propositions"][number]) => JSON.stringify([
    claim.context.crop, claim.context.soil_band, claim.context.water_band, claim.context.season,
    claim.context.climate_phase, claim.context.crew, claim.context.protocol,
  ]);
  if (new Set(science.propositions.map((claim) => `${claim.recipe}:${contextKey(claim)}`)).size !== science.claims
    || data.cycles.some((cycle) => {
      const [a, b] = cycle.claims.map((id) => science.propositions[id]);
      return a.recipe === b.recipe || contextKey(a) !== contextKey(b);
    })) return invalid;
  // The Phase 4 topic cannot be recovered from a later Phase 10 belief or recipe.
  if (!Array.isArray(science.allocations) || science.allocations.length > 40 || science.allocations.some((row) => {
    if (!object(row)) return true;
    if (row.claim_id == null) return !(source === data.enabled_turn && data.cycles[0]?.legacy_adopted);
    return !integer(row.claim_id) || science.propositions[row.claim_id]?.recipe !== row.recipe;
  })) return invalid;
  return { status: "known", record: data };
}

export function researchReason(reason: string): string {
  const known: Record<string, string> = {
    no_eligible_academy: "No eligible academy", projected_treasury_floor: "Projected treasury below the funding floor",
    registered_context_or_access_unavailable: "Registered context or academy access unavailable",
    no_eligible_received_question: "No eligible academy has received this cycle's question", original_not_funded: "Original trial was not funded",
    funding_window_elapsed: "Funding window elapsed", research_paused: "Research paused", legacy_activation: "Legacy schedule closed at activation",
  };
  return known[reason] ?? reason.replaceAll("_", " ");
}
