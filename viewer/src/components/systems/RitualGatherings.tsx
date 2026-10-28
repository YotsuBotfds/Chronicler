import { useMemo, useState } from "react";
import { gatheringHistory, gatheringRows } from "../../lib/ritualGatherings";
import { hasObservation, observationAt } from "../../lib/observedSystems";
import type { SystemPanelProps } from "../../lib/systems";
import { StatTile, StripLegend, TurnStrip } from "./SystemParts";

const show = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const HISTORY_LIMIT = 40;

/** Actual local gatherings, resource receipts and schedules at the selected point. */
export function RitualGatherings({ bundle, snapshot, currentTurn, onSeek, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const at = snapshot?.turn ?? currentTurn;
  const record = observationAt(snapshot, "ritual_gatherings");
  const history = useMemo(() => gatheringHistory(bundle.history, at), [bundle.history, at]);
  const rows = useMemo(() => gatheringRows(bundle.history, at), [bundle.history, at]);
  if (!hasObservation(bundle.history, "ritual_gatherings")) return null;
  if (!record) return <section className="systems-section" aria-label="Harvest gatherings">
    <h3>Harvest gatherings</h3><p className="systems-note">No gathering observation at turn {currentTurn}. Schedules, attendance and spending are unknown here.</p>
  </section>;
  const visible = expanded ? history : history.slice(0, HISTORY_LIMIT);
  return <section className="systems-section" aria-label="Harvest gatherings">
    <h3>Harvest gatherings · snapshot {at}</h3>
    <p className="systems-note">Records after simulation turn {record.source_turn}. Attendance is local and recorded, food and treasury are actually consumed or spent. Bond operations are attempts, not a count of new bonds. No spiritual, legitimacy or practice bonus is inferred.</p>
    <div className="systems-tiles">
      <StatTile label="Gatherings held" value={record.counters.held ?? "Not recorded"} detail="so far" />
      <StatTile label="Gatherings cancelled" value={record.counters.cancelled ?? "Not recorded"} detail="so far" />
      <StatTile label="Recorded attendances" value={record.counters.attendees ?? "Not recorded"} detail="across occurrences; people may attend again" />
      <StatTile label="Food consumed" value={record.counters.food == null ? "Not recorded" : show(record.counters.food)} detail="grain units so far" />
      <StatTile label="Treasury spent" value={record.counters.funds ?? "Not recorded"} detail="so far" />
    </div>
    <h4>Recorded occurrences</h4>
    <StripLegend items={[{ label: "held", color: "#5aa88f" }, { label: "cancelled", color: "#7d8a96" }]} />
    <TurnStrip rows={rows} firstTurn={bundle.history[0]?.turn ?? at} endTurn={at + 1} currentTurn={at}
      label="Harvest gathering occurrences over time" emptyText="No actual gathering occurrence is recorded by this snapshot."
      onSeek={onSeek} onSelectRow={(row) => { const first = history.find((item) => item.gathering_id === row.id); if (first) onSelectRegion(first.region_name); }} />
    <p className="systems-note">Marks refer to the snapshot containing each completed occurrence. Blank intervals are not claims that a gathering happened or failed.</p>
    {visible.length > 0 && <div className="systems-table-wrap"><table className="systems-table" aria-label={`Gathering history through snapshot ${at}`}>
      <thead><tr><th>Simulation turn / snapshot</th><th>Region</th><th>Host then</th><th>Faith then</th><th>Status</th><th>Reason</th><th>Attendees</th><th>Food consumed</th><th>Treasury spent</th><th>Contact units</th><th>Bond attempts</th></tr></thead>
      <tbody>{visible.map((row) => <tr key={`${row.gathering_id}@${row.turn}`}>
        <td><button type="button" className="systems-link" onClick={() => onSeek(row.snapshot_turn)}>{row.turn} / {row.snapshot_turn}</button></td>
        <td><button type="button" className="systems-link" onClick={() => onSelectRegion(row.region_name)}>{row.region_name}</button></td>
        <td>{row.host_name ? <button type="button" className="systems-link" onClick={() => onSelectCivilization(row.host_name!)}>{row.host_name}</button> : "Not recorded"}</td>
        <td>{row.faith_name ?? "Not recorded"}</td><td>{row.status}</td><td>{row.reason ?? "—"}</td>
        <td><details><summary>{row.attendee_ids.length} recorded agents</summary><span>{row.attendee_ids.length ? row.attendee_ids.join(", ") : "No attendees recorded"}</span></details></td>
        <td>{show(row.food)}</td><td>{row.funds}</td><td>{show(row.contact_units)}</td><td>{row.bond_ops}</td>
      </tr>)}</tbody>
    </table></div>}
    {history.length > HISTORY_LIMIT && <button type="button" className="phase75-ghost-button" onClick={() => setExpanded(!expanded)}>
      {expanded ? "Show recent occurrences" : `Show all ${history.length} recorded occurrences`}
    </button>}
    <h4>Schedules known at this snapshot</h4>
    <p className="systems-note">A scheduled turn is a plan, not evidence of future attendance. Regional schedule identity persists when rulers change.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Gathering schedules at snapshot ${at}`}>
      <thead><tr><th>Gathering</th><th>Region</th><th>Cadence</th><th>Next scheduled turn</th><th>Last turn</th><th>Last status</th></tr></thead>
      <tbody>{record.schedules.map((row) => <tr key={row.gathering_id}><td>{row.gathering_id}</td>
        <td>{row.region_name}</td><td>Every {row.cadence} turns</td><td>{row.next_turn}</td>
        <td>{row.last_turn ?? "None recorded"}</td><td>{row.last_status ?? "None recorded"}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}
