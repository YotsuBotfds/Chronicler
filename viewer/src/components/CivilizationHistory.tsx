import { useMemo, useState } from "react";
import type { Bundle, Event } from "../types";
import { civilizationHistory, type CivilizationHistoryEntry, type CivilizationHistoryEvent } from "../lib/civilizationHistory";
import "./civilization-history.css";

export interface CivilizationHistoryProps {
  bundle: Bundle;
  currentTurn: number;
  /** Stable index in world_state.civilizations. */
  civilizationIndex: number;
  onSeek?: (turn: number) => void;
  onInspectEvent?: (event: Event) => void;
  onInspectRegion?: (regionIndex: number, name: string) => void;
}
const display = (value: number | null) => value === null ? "Unknown" : value.toLocaleString();

export function CivilizationHistory(props: CivilizationHistoryProps) {
  const result = useMemo(() => civilizationHistory(props.bundle, props.currentTurn, props.civilizationIndex),
    [props.bundle, props.currentTurn, props.civilizationIndex]);
  return <section className="civilization-history" aria-label="Civilization life history">
    <h2>Civilization life history{result.name ? `: ${result.name}` : ""}</h2>
    <p>World civilization index {props.civilizationIndex}. Recorded history through selected turn {props.currentTurn}; inspection and filters keep this turn.</p>
    <p role="status">{result.status}.</p>
    <HistorySequence key={`${props.civilizationIndex}:${props.currentTurn}`} entries={result.entries} {...props} />
    <h3>Recorded lineage</h3>
    {result.lineage.length === 0 ? <p>No unambiguous recorded parent or successor relationship in this bounded history.</p>
      : <ul>{result.lineage.map((line, index) => <li key={`${line.visibleTurn}:${index}`}>
        T{line.visibleTurn}: recorded secession from {line.parentName} (index {line.parentIndex}) to {line.childName} (index {line.childIndex}).
        <small>Source: {line.source}. Both identities have exact rows at this completed turn. This does not establish any later succession.</small>
      </li>)}</ul>}
    <details><summary>Sources and selection rules</summary><ul>{result.notes.map((note) => <li key={note}>{note}</li>)}</ul>
      <p>Values are population, treasury, stability and military from the dated row, plus its leader name, era, region list and alive flag. No final-world values, founded_turn or current leader fill historical gaps. All event types explicitly naming this civilization are included; attribution alone does not establish a cause.</p>
    </details>
  </section>;
}
function HistorySequence({ entries, onSeek, onInspectEvent, onInspectRegion }: CivilizationHistoryProps & { entries: CivilizationHistoryEntry[] }) {
  const [limit, setLimit] = useState(20);
  const [filter, setFilter] = useState("all");
  const matching = entries.filter((entry) => filter === "all" || (filter === "events" ? entry.events.length > 0
    : filter === "changes" ? entry.observations.length > 0 : !entry.recorded));
  const visible = matching.slice(-limit);
  return <>
    <label className="civilization-history-filter">Entries shown<select aria-label="Civilization history entries" value={filter}
      onChange={(event) => { setFilter(event.target.value); setLimit(20); }}>
      <option value="all">All recorded turns and event dates</option><option value="events">Recorded events</option>
      <option value="changes">Observed changes and first observation</option><option value="missing">Missing or ambiguous rows</option>
    </select></label>
    <p>Showing the latest {visible.length} of {matching.length} matching dates, in chronological order.</p>
    {matching.length > limit && <button type="button" onClick={() => setLimit(limit + 20)}>Show earlier dates ({matching.length - limit} remaining)</button>}
    {matching.length === 0 && <p>No matching dated records. Missing history is not evidence that nothing happened.</p>}
    <ol className="civilization-history-sequence">{visible.map((entry) => <li key={entry.turn}>
      <div className="civilization-history-date"><h3>Turn {entry.turn}</h3>
        {onSeek && entry.recorded && <button type="button" onClick={() => onSeek(entry.turn)}>View turn {entry.turn}</button>}</div>
      <p>{entry.status}. {entry.alive !== null && <>Recorded alive flag: {entry.alive ? "true" : "false"}.</>}</p>
      <small>Source: {entry.source}</small>
      {entry.recorded ? <>
        <dl className="civilization-history-values"><div><dt>Population</dt><dd>{display(entry.population)}</dd></div>
          <div><dt>Treasury</dt><dd>{display(entry.treasury)}</dd></div><div><dt>Stability</dt><dd>{display(entry.stability)}</dd></div>
          <div><dt>Military</dt><dd>{display(entry.military)}</dd></div><div><dt>Leader name</dt><dd>{entry.leader ?? "Unknown"}</dd></div>
          <div><dt>Era</dt><dd>{entry.era ?? "Unknown"}</dd></div></dl>
        <p>Recorded regions ({entry.regions?.length ?? "unknown"}): {entry.regions === null ? "Unknown" : entry.regions.length === 0 ? "None"
          : entry.regions.map((region, index) => <span key={region.name}>{index > 0 ? ", " : ""}{onInspectRegion && region.regionIndex !== null
            ? <button type="button" onClick={() => onInspectRegion(region.regionIndex!, region.name)}>Inspect region: {region.name}</button>
            : region.name}</span>)}</p>
      </> : <p>Values unknown at this date. Earlier rows are not carried forward.</p>}
      {entry.observations.length > 0 && <ul>{entry.observations.map((observation) => <li key={observation}>{observation}</li>)}</ul>}
      <HistoryEvents key={entry.turn} refs={entry.events} onInspectEvent={onInspectEvent} />
    </li>)}</ol>
  </>;
}
function HistoryEvents({ refs, onInspectEvent }: { refs: CivilizationHistoryEvent[]; onInspectEvent?: CivilizationHistoryProps["onInspectEvent"] }) {
  const [limit, setLimit] = useState(6);
  if (refs.length === 0) return null;
  return <div className="civilization-history-events"><h4>Explicitly attributed events ({refs.length})</h4>
    <ul>{refs.slice(0, limit).map((ref, index) => <li key={`${ref.source}:${index}`}>
      <strong>{ref.event.event_type}</strong> (simulation tick {ref.event.turn}, visible at T{ref.visibleTurn}): {ref.event.description}
      <small>Source: {ref.source}</small>
      {onInspectEvent && ref.inspectable && ref.timelineEvent && <button type="button" onClick={() => onInspectEvent(ref.timelineEvent!)}>Inspect event: {ref.event.event_type}</button>}
      {!ref.inspectable && <p>{ref.timelineEvent ? "Event selection is unavailable because its key is ambiguous." : "Named event preserved as a source record; no selectable timeline event is assumed."}</p>}
    </li>)}</ul>
    {refs.length > limit && <button type="button" onClick={() => setLimit(limit + 6)}>Show more events ({refs.length - limit} remaining)</button>}
  </div>;
}
