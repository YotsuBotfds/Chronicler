import { useMemo, useState } from "react";
import { hasObservation, observationAt, observationEventKnown, SCIENTIFIC_EVENT_TYPES } from "../../lib/observedSystems";
import { scientificClaimsSeries, scientificContext, scientificPublication, scientificTrials } from "../../lib/scientificClaims";
import { eventByKey } from "../../lib/bundleIndex";
import { eventsOfTypes, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, SystemEventList } from "./SystemParts";

const show = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 3 });
const percent = (n: number) => `${show(100 * n)}%`;
const HISTORY_LIMIT = 40;
const SCIENCE_EVENTS = new Set<string>(SCIENTIFIC_EVENT_TYPES);

/** Institutional information and paid effort; no confidence-to-yield inference. */
export function ScientificClaims({ bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const at = snapshot?.turn ?? currentTurn;
  const record = observationAt(snapshot, "scientific_claims");
  const history = useMemo(() => scientificTrials(bundle.history, at), [bundle.history, at]);
  const series = useMemo(() => scientificClaimsSeries(bundle.history, at), [bundle.history, at]);
  if (!hasObservation(bundle.history, "scientific_claims")) return null;
  if (!record) return <section className="systems-section" aria-label="Academy claims and evidence">
    <h3>Academy claims and evidence</h3><p className="systems-note">No usable scientific-claims observation at turn {currentTurn}. Missing, stale or future-dated evidence leaves local confidence, trials and spending unknown.</p>
  </section>;
  const visible = expanded ? history : history.slice(0, HISTORY_LIMIT);
  const publication = scientificPublication(record.publication_rule);
  const seatName = (id: number) => record.beliefs.find((row) => row.seat === id)?.seat_name ?? `Seat ${id}`;
  const regionName = (id: number) => record.beliefs.find((row) => row.region === id)?.region_name ?? null;
  const events = eventsOfTypes(bundle.events_timeline, SCIENTIFIC_EVENT_TYPES, currentTurn)
    .filter((event) => observationEventKnown(event, record.source_turn));
  const eventLink = (id: string | undefined, label: string) => {
    const event = id ? eventByKey(bundle.events_timeline, id) : null;
    return event && SCIENCE_EVENTS.has(event.event_type) && event.turn <= record.source_turn
      ? <button type="button" className="systems-link" onClick={() => onSelectEvent(event)}>{label}</button> : null;
  };
  return <section className="systems-section" aria-label="Academy claims and evidence">
    <h3>Academy claims and evidence · snapshot {at}</h3>
    <p className="systems-note">Recorded after simulation turn {record.source_turn}. {record.active ? "The pilot is active." : "The pilot is enabled but dormant."} Confidence is a local policy score for a contextual proposition, not a probability that a technique is universally true. Information allocates ordinary paid adoption effort; it does not directly change yields.</p>
    <p className="systems-note" aria-label="Scientific publication policy"><strong>Publication policy at this snapshot: {publication.label}.</strong> {publication.detail}</p>
    <div className="systems-tiles">
      <StatTile label="Propositions" value={record.claims} detail={`${record.seats} participating seats`} />
      <StatTile label="Completed trials" value={record.completed} detail={`${record.cancelled} cancelled; ${record.failed} failed`} />
      <StatTile label="Trial spending" value={record.trial_spent} detail="actual treasury paid so far" />
      <StatTile label="Adoption effort spending" value={record.effort_spent} detail="actual treasury paid so far" />
      <StatTile label="Evidence receipts" value={record.evidence_receipts} detail={`${record.pending_messages} messages pending`} />
      <StatTile label="Withheld results" value={record.withheld_results} detail={`${record.expired_messages} messages expired`} />
    </div>
    <p className="systems-note">Controls: information {record.controls.withhold_information ? "withheld" : "available"}; transmission {record.controls.transmission_enabled ? "enabled" : "disabled"}; {record.controls.uninformative_tests ? "sham measurements with no treatment information" : "ordinary noisy measurements"}. Sham measurements still undergo ordinary posterior updates.</p>
    <CivLineChart data={series} civs={["Trial spending", "Adoption effort spending"]}
      color={(name) => name === "Trial spending" ? "#9a7fc4" : "#5aa88f"} currentTurn={at} label="Recorded scientific spending over time" step />
    <h4>Contextual propositions</h4>
    {record.propositions.length === 0 ? <p className="systems-note">No proposition recorded.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Scientific propositions at snapshot ${at}`}>
        <thead><tr><th>Claim</th><th>Recipe</th><th>Proposed / origin seat</th><th>Registered context</th><th>Support threshold</th></tr></thead>
        <tbody>{record.propositions.map((row) => <tr key={row.id}><td>{row.id} {eventLink(row.event_id, "Proposal event")}</td><td>{row.recipe}</td><td>{row.proposed_turn ?? "Date not recorded"} / {seatName(row.origin_seat)}</td>
          <td>{scientificContext(row.context)}</td><td>{percent(row.threshold)} relative grain output</td></tr>)}</tbody>
      </table></div>}
    <h4>Current-context policy confidence</h4>
    <p className="systems-note">Dependence groups deduplicate source blocks in the policy's evidence accounting. Their count does not establish independent world units or replication quality. A seat with no applicable received evidence retains the prior score. Archived receipts can remain when a change of season, ecology or climate makes their proposition inapplicable to the current policy.</p>
    {record.beliefs.length === 0 ? <p className="systems-note">No local belief observation recorded.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Scientific beliefs at snapshot ${at}`}>
        <thead><tr><th>Seat</th><th>Region</th><th>Ruler then</th><th>Claim</th><th>Local confidence</th><th>Dependence groups</th><th>Last evidence used by policy</th></tr></thead>
        <tbody>{record.beliefs.map((row) => <tr key={`${row.seat}:${row.claim}`}><td>{row.seat_name}</td>
          <td><button type="button" className="systems-link" onClick={() => onSelectRegion(row.region_name)}>{row.region_name}</button></td>
          <td>{row.owner_name ? <button type="button" className="systems-link" onClick={() => onSelectCivilization(row.owner_name!)}>{row.owner_name}</button> : "No ruler recorded"}</td>
          <td>{row.claim}</td><td>{percent(row.confidence)}</td><td>{row.independent_groups}</td><td>{row.last_evidence_turn ?? "None applicable"} {eventLink(row.last_evidence_event_id, "Evidence event")}</td></tr>)}</tbody>
      </table></div>}
    <h4>Paid adoption allocations in simulation turn {record.source_turn}</h4>
    <p className="systems-note">Actual treasury paid this completed turn: {show(record.allocations.reduce((sum, row) => sum + row.paid, 0))}. The whole seat payment is recorded on its first allocation row; a zero on another recipe is not a separate free programme.</p>
    {record.allocations.length === 0 ? <p className="systems-note">No paid allocation recorded this completed turn.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Scientific allocations at snapshot ${at}`}>
        <thead><tr><th>Seat</th><th>Region</th><th>Recipe</th><th>Effort share</th><th>Confidence used</th><th>Treasury paid</th></tr></thead>
        <tbody>{record.allocations.map((row, i) => <tr key={`${row.seat}:${row.recipe}:${i}`}><td>{seatName(row.seat)}</td>
          <td>{regionName(row.region) ? <button type="button" className="systems-link" onClick={() => onSelectRegion(regionName(row.region)!)}>{regionName(row.region)}</button> : `Region ${row.region}`}</td>
          <td>{row.recipe}</td><td>{percent(row.share)}</td><td>{percent(row.confidence)}</td><td>{row.paid} {eventLink(row.event_id, "Allocation event")}</td></tr>)}</tbody>
      </table></div>}
    <h4>Dated trial resolutions</h4>
    <p className="systems-note">Only resolutions saved by this snapshot appear below. Trial calculations use a fixed crew; their outputs are not added harvest. Noisy measured outputs and support classifications are distinct from the modelled trial outputs. Cancelled and failed trials have no completed measurement here.</p>
    {visible.length === 0 ? <p className="systems-note">No dated trial resolution recorded by this snapshot.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Scientific trial history through snapshot ${at}`}>
        <thead><tr><th>Resolved / snapshot</th><th>Trial / parent</th><th>Recipe / seat</th><th>Status</th><th>Trial cost</th><th>Measurement and provenance</th></tr></thead>
        <tbody>{visible.map((row) => <tr key={`${row.funded_turn}:${row.id}:${row.resolved_turn}`}>
          <td><button type="button" className="systems-link" onClick={() => onSeek(row.snapshot_turn)}>{row.resolved_turn} / {row.snapshot_turn}</button></td>
          <td>{row.id} / {row.parent < 0 ? "original" : row.parent}</td><td>{row.recipe} · {row.seat_name}</td><td>{row.status}{row.reason ? `: ${row.reason}` : ""}</td>
          <td>{row.cost} treasury · payer index {row.payer}</td><td><details><summary>Recorded trial details</summary>
            <div>Funded {row.funded_turn}; scheduled completion {row.completion_turn}; resolved {row.resolved_turn}.</div>
            <div>{eventLink(row.funded_event_id, "Funding event")} {eventLink(row.event_id, "Resolution event")}</div>
            <div>{scientificContext(row.inputs.context)}</div>
            {row.status === "completed" && <><div>Modelled grain output, control / treatment: {show(row.control_output)} / {show(row.treatment_output)}.</div>
              <div>Measured grain output, control / treatment: {row.observed_control == null ? "Not recorded" : show(row.observed_control)} / {row.observed_treatment == null ? "Not recorded" : show(row.observed_treatment)}.</div>
              <div>Reported support: {row.supports == null ? "Unscored" : row.supports ? "Yes" : "No"}; usable measurement: {row.informative ? "Yes" : "No"}.</div></>}
            <div>Source data: {row.source_data || "Not recorded"}; environment: {row.environment_block || "Not recorded"}; dependence group: {row.dependence_group || "Not recorded"}.</div>
          </details></td>
        </tr>)}</tbody>
      </table></div>}
    {history.length > HISTORY_LIMIT && <button type="button" className="phase75-ghost-button" onClick={() => setExpanded(!expanded)}>{expanded ? "Show recent trials" : `Show all ${history.length} recorded resolutions`}</button>}
    <SystemEventList events={events} label="Scientific claims events" emptyText="No scientific event recorded by this source turn." onSelectEvent={onSelectEvent} />
    <p className="systems-note">History stops at this snapshot. Missing observations remain gaps; final world state supplies no historical values.</p>
  </section>;
}
