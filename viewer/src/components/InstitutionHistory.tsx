import { useMemo, useState } from "react";
import type { Bundle, Event } from "../types";
import { institutionObservationValues, readInstitutionHistory, type InstitutionHistoryReading, type InstitutionHistorySelection } from "../lib/institutionHistory";
import "./institution-history.css";

export interface InstitutionHistoryProps {
  bundle: Bundle;
  currentTurn: number;
  selection: InstitutionHistorySelection | null;
  onSelectEvent?: (event: Event) => void;
  onInspectRelated?: (entity: { kind: "region" | "civilization"; name: string }) => void;
  onViewRecordedTurn?: (turn: number) => void;
}
export function InstitutionHistory({ bundle, currentTurn, selection, ...actions }: InstitutionHistoryProps) {
  const reading = useMemo(() => readInstitutionHistory(bundle, currentTurn, selection), [bundle, currentTurn, selection]);
  return <section className="institution-history" aria-label="City institutional history">
    <h3>City institutional history</h3>
    <p>City histories are supported here. Learning-seat and guild lifecycles are not yet covered.</p>
    {!reading.supported ? <p role="status">{reading.status}</p> : <HistoryDetails key={`${reading.id}:${currentTurn}`} reading={reading} {...actions} />}
  </section>;
}
function HistoryDetails({ reading, onSelectEvent, onInspectRelated, onViewRecordedTurn }: { reading: InstitutionHistoryReading } & Pick<InstitutionHistoryProps, "onSelectEvent" | "onInspectRelated" | "onViewRecordedTurn">) {
  const [limit, setLimit] = useState(8);
  const selected = reading.selected!;
  return <>
    <h4>{reading.name} · settlement ID {reading.id}</h4>
    <p>Through selected snapshot {reading.through}. First observed {reading.firstRecordedTurn ?? "unknown"}; last observed {reading.lastRecordedTurn ?? "unknown"}.</p>
    <p role="status">{reading.status}</p>
    {selected.row && <dl className="institution-history-values">{institutionObservationValues(selected.row).map((field) => <div key={field.key}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>}
    {onInspectRelated && <div className="institution-history-actions">{reading.related.map((entity) => <button key={entity.kind} type="button" onClick={() => onInspectRelated(entity)}>Inspect {entity.kind}: {entity.name}</button>)}</div>}
    <details><summary>Selected observation source</summary><code>{selected.sourceRef}</code></details>
    <h4>Dated lifecycle records</h4>
    <p>Recorded falls describe the backend record; missing rows do not establish destruction. History and event dates use completed snapshots below.</p>
    {reading.moments.length === 0 && <p>No explicit lifecycle moments recorded through this turn. Founding and loss dates remain unknown.</p>}
    <ol className="institution-history-list">{reading.moments.slice(0, limit).map((moment) => <li key={moment.sourceRef}>
      <strong>{moment.kind.replace(/_/g, " ")} · snapshot {moment.turn} (source tick {moment.sourceTurn})</strong>
      {moment.event && <p>{moment.event.description}</p>}<p>{moment.status}</p>
      <div className="institution-history-actions">
        {onSelectEvent && moment.event && <button type="button" onClick={() => onSelectEvent(moment.event!)}>Inspect recorded event: {moment.kind}</button>}
        {onViewRecordedTurn && moment.turn !== reading.through && <button type="button" onClick={() => onViewRecordedTurn(moment.turn)}>View snapshot {moment.turn}</button>}
      </div>
      <details><summary>Moment sources</summary><code>{moment.sourceRef}</code>{moment.eventRef && <code>{moment.eventRef}</code>}</details>
    </li>)}</ol>
    <h4>Recorded endpoint changes</h4>
    <p>Changes compare stated endpoints. Ownership changes are observations; changes in residents, purse or wares do not establish an institution's causal benefit or recovery.</p>
    {reading.changes.length === 0 && <p>No comparable changed endpoints recorded through this turn.</p>}
    <ol className="institution-history-list">{reading.changes.slice().reverse().slice(0, limit).map((change) => <li key={`${change.from}:${change.to}`}>
      <strong>Snapshots {change.from} → {change.to}</strong>
      <p>{change.continuousCoverage ? "Adjacent recorded endpoints; timing is bounded by this snapshot interval." : "Sparse endpoint window; institutional continuity and change timing are unknown."}</p>
      <ul>{change.fields.map((field) => <li key={field.label}>{field.label}: {field.before} → {field.after}{field.delta !== null ? ` (change ${field.delta > 0 ? "+" : ""}${Number(field.delta.toFixed(4))})` : ""}
        <details><summary>{field.label} sources</summary><code>{field.beforeSource}</code><code>{field.afterSource}</code></details>
      </li>)}</ul>
    </li>)}</ol>
    <h4>Observation coverage</h4>
    <ol className="institution-history-list">{reading.observations.slice().reverse().slice(0, limit).map((observation) => <li key={observation.turn}>
      <strong>Snapshot {observation.turn}: {observation.status}</strong><p>{observation.explanation}</p>
      {observation.row && <p>{observation.row.name}; region {observation.row.region ?? "not recorded"}; lord {observation.row.lord ?? "not recorded"}.</p>}
      <details><summary>Observation source</summary><code>{observation.sourceRef}</code></details>
    </li>)}</ol>
    <p>Showing up to {limit} recent entries per list.</p>
    {Math.max(reading.observations.length, reading.changes.length, reading.moments.length) > limit && <button type="button" onClick={() => setLimit(limit + 8)}>Show 8 more history entries</button>}
    <details><summary>History scope and limits</summary><ul>{reading.coverage.map((line) => <li key={line}>{line}</li>)}</ul></details>
  </>;
}
