import { useState } from "react";
import type { Bundle, HouseholdMobilitySample } from "../types";
import { householdMobilityAt } from "../lib/householdMobility";

const PAGE_SIZE = 8;
const groups = (n: number) => `${n} ${n === 1 ? "group" : "groups"}`;
const people = (n: number) => `${n} native ${n === 1 ? "person" : "people"}`;
const amount = (n: number) => n === 0 ? "0" : Math.abs(n) < .001
  ? n.toExponential(3) : n.toLocaleString(undefined, { maximumFractionDigits: 3 });
const reason: Record<HouseholdMobilitySample["reason"], string> = {
  sufficient: "Passed: liquid requirement met",
  insufficient: "Blocked: insufficient liquid wealth",
  no_local_distress: "Passed: no local distress gate",
  unknown_destination: "Passed: destination or route unavailable to the gate",
  on_trip: "Passed: already on a trip",
};

/** Gate observations sit alongside, not inside, recorded migration flows. */
export function HouseholdMobilityEvidence({ bundle, turn, selectedRegionIndex }: {
  bundle: Bundle; turn: number; selectedRegionIndex?: number | null;
}) {
  const scope = `${turn}:${selectedRegionIndex ?? "all"}`;
  const [page, setPage] = useState({ scope, limit: PAGE_SIZE });
  if (page.scope !== scope) setPage({ scope, limit: PAGE_SIZE });
  const limit = page.scope === scope ? page.limit : PAGE_SIZE;
  const regions = bundle.world_state.regions;
  const selected = selectedRegionIndex ?? null;
  const validRegion = selected === null || (Number.isSafeInteger(selected) && selected >= 0 && selected < regions.length);
  const frame = validRegion ? householdMobilityAt(bundle, turn) : null;
  const regionName = (id: number) => regions[id] ? `${regions[id].name} (#${id})` : `Unknown region (#${id})`;
  if (!frame) return <section aria-label="Household mobility gate">
    <h4>Household mobility gate</h4><p>Gate observations are not recorded or unavailable at this snapshot.</p>
  </section>;
  const samples = frame.samples.filter((row) => selected === null || row.origin_region_id === selected || row.destination_region_id === selected);
  return <section aria-label="Household mobility gate">
    <h4>Household mobility gate · snapshot {frame.completed_turn}</h4>
    <p>Native decision after consolidation in simulation turn {frame.source_turn}. Passing this gate does not establish that a move occurred. Counts below cover the whole recorded world, including groups outside the selected region.</p>
    <p>Proposed: <strong>{groups(frame.proposed_groups)} / {people(frame.proposed_native_persons)}</strong> · Passed: <strong>{groups(frame.passed_groups)} / {people(frame.passed_native_persons)}</strong> · Blocked: <strong>{groups(frame.blocked_groups)} / {people(frame.blocked_native_persons)}</strong>.</p>
    <p>Requirement: {amount(frame.requirement_per_native_person)} native agent wealth units per native person. Available liquid wealth is the recorded sum for native adults in each sampled group.</p>
    <p>{frame.dropped_samples} {frame.dropped_samples === 1 ? "group sample" : "group samples"} omitted from the retained record; world counts above include them. {selected === null ? "All retained samples" : "Retained samples involving the selected region"}: {samples.length}. These samples do not establish regional totals.</p>
    {samples.length === 0 ? <p>No retained gate samples match this selection.</p> : <>
      <ol className="migration-evidence-flows" aria-label="Household mobility gate samples">
        {samples.slice(0, limit).map((row, index) => <li key={`${row.group_id}:${index}`}>
          <p>Group {row.group_id}: {regionName(row.origin_region_id)} → {regionName(row.destination_region_id)} · {people(row.native_persons)}</p>
          <p>{reason[row.reason]}. Native adult liquid wealth available: {amount(row.native_adult_liquid_wealth)}; required: {amount(row.required_liquid)}.</p>
        </li>)}
      </ol>
      <p>Showing {Math.min(limit, samples.length)} of {samples.length} matching retained samples.</p>
      {limit < samples.length && <button type="button" onClick={() => setPage({ scope, limit: limit + PAGE_SIZE })}>Show more gate samples ({samples.length - limit} remaining)</button>}
    </>}
  </section>;
}
