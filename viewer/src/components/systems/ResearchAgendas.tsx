import type { ReactNode } from "react";
import type { ScientificResearchAgendas } from "../../expansionTypes";
import { RESEARCH_CAPACITIES, researchReason } from "../../lib/researchAgendas";

export function ResearchAgendas({ record, source, eventLink }: {
  record: ScientificResearchAgendas;
  source: number;
  eventLink: (id: string | undefined, label: string) => ReactNode;
}) {
  const current = record.cycles.find((cycle) => cycle.id === record.current_cycle_id);
  return <div aria-label="Finite research agendas">
    <h4>Finite retained research agendas</h4>
    <p className="systems-note"><strong>New research {record.enabled ? "enabled" : "paused"}.</strong> Agenda mode activated in simulation turn {record.enabled_turn}.
      {current ? ` Funding cycle ${current.id} is open: originals through turn ${current.original_deadline}, all funding through turn ${current.funding_deadline} (inclusive).`
        : " No funding cycle is open."} The next cycle can open no earlier than turn {record.next_open_turn}; eligibility and capacity can delay it.</p>
    {!record.enabled && <p className="systems-note">The pause stops new agendas and trial funding. Already-paid trials, messages, retained evidence and ordinary paid adoption can continue when eligible.</p>}
    {record.blocked_reason && <p className="systems-note">Recorded blockage at turn {record.blocked_turn}: {researchReason(record.blocked_reason)}.</p>}
    <p className="systems-note">Each new cycle fixes its recipient seats at opening. A new or replacement academy does not inherit another seat's receipts; old results are not automatically rebroadcast to a later cycle.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Research capacity after simulation turn ${source}`}>
      <thead><tr><th>Retained capacity</th><th>Used</th><th>Reserved</th><th>Limit</th></tr></thead>
      <tbody>{Object.entries(RESEARCH_CAPACITIES).map(([key, spec]) => {
        const row = record.capacity[key as keyof typeof record.capacity];
        return <tr key={key}><td>{spec.label}</td><td>{row.used}</td><td>{row.reserved}</td><td>{row.limit}</td></tr>;
      })}</tbody>
    </table></div>
    <p className="systems-note">Reservations hold record space; they are not treasury payments. Retained archive counts: {record.archive.retained_topics} topics, {record.archive.retained_trials} paid trials, {record.archive.retained_proposals} question receipts and {record.archive.retained_receipts} evidence receipts. The simulation retains raw records, but this export supplies trial details only when resolved in its source turn. Complete historical trial and receipt contents are not inferred from these counts.</p>
    <p className="systems-note">Paid adoption retains its {record.effort_cadence}-turn calendar{record.effort_started_turn === null ? "; its first payment anchor is not recorded yet" : ` anchored at turn ${record.effort_started_turn}`}.
      {record.paid_use_seasons.length > 0 && ` Eligible payment seasons are ${record.paid_use_seasons.join(", ")} (season indexes 0–3).`} Research can record topics outside those seasons; no paid use or efficacy result is implied for them.</p>
    <details><summary>Recorded agenda cycles ({record.cycles.length})</summary>
      {record.cycles.length === 0 ? <p className="systems-note">No agenda has opened.</p> :
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Research cycle ledger after simulation turn ${source}`}>
          <thead><tr><th>Cycle / origin</th><th>Actual dates</th><th>Funding plans</th><th>Topics / paid trials</th><th>Recipients and unfilled opportunities</th></tr></thead>
          <tbody>{record.cycles.map((cycle) => <tr key={cycle.id}>
            <td>{cycle.id} · Seat {cycle.origin_seat}{cycle.legacy_adopted ? " · adopted legacy" : ""} {eventLink(cycle.announcement_event_id, "Agenda announcement")}</td>
            <td>Opened: {cycle.opened_turn ?? "Not recorded"}. {cycle.closed_turn === null ? "Open for funding." : `Closed: ${cycle.closed_turn} · ${researchReason(cycle.close_reason)}.`}</td>
            <td>{cycle.legacy_adopted ? "Historical funding deadlines unknown; new windows are not applied retrospectively." :
              <>Originals through {cycle.original_deadline}; all funding through {cycle.funding_deadline}. Next opening no earlier than {cycle.next_open_not_before}.</>}</td>
            <td>Topics: {cycle.claims.join(", ")}. Paid trial IDs: {cycle.trials.length ? cycle.trials.join(", ") : "None"}.</td>
            <td>{cycle.opening_roster_complete ? "Recipients frozen at actual opening" : "Historical opening roster unknown; seats observed at legacy activation"}: {cycle.participants.length ? cycle.participants.map((id) => `Seat ${id}`).join(", ") : "None recorded"}.
              {cycle.closed_turn !== null && <div>Unfunded originals: {cycle.unfunded_originals.join(", ") || "None"}; unfunded replications: {cycle.unfunded_replications.join(", ") || "None"}. These are unpaid opportunities, not failed trials.</div>}
              {[...new Set([...Object.keys(cycle.slot_reasons), ...cycle.unfunded_originals.map((id) => `original:${id}`),
                ...cycle.unfunded_replications.map((id) => `replication:${id}`)])].map((slot) => <div key={slot}>{slot.replace(":", " for topic ")}: {cycle.slot_reasons[slot] ? researchReason(cycle.slot_reasons[slot]) : "Reason not recorded"}.</div>)}
            </td>
          </tr>)}</tbody>
        </table></div>}
    </details>
  </div>;
}
