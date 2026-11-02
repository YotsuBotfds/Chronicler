import { useMemo, useState } from "react";
import type { Bundle, Event } from "../types";
import { changeEvents, compareReadings, comparisonEntities, comparisonTurns, largestRelativeChanges,
  readEntityTurn, type HistoryEntity, type ChangeEvent } from "../lib/historyComparison";
import "./turn-changes.css";

interface Props {
  bundle: Bundle; currentTurn: number; selectedRegion?: string | null; selectedCivilization?: string | null;
  onSeek: (turn: number) => void; onSelectEvent?: (event: Event) => void;
}
const key = (entity: HistoryEntity) => JSON.stringify([entity.kind, entity.name]);
const numbers = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const format = (value: number | null) => value === null ? "Not recorded" : numbers.format(value);
const signed = (value: number | null) => value === null ? "Unavailable" : `${value > 0 ? "+" : ""}${format(value)}`;

function RecordedEvents({ rows, onSeek, onSelectEvent }: {
  rows: ChangeEvent[]; onSeek: Props["onSeek"]; onSelectEvent: Props["onSelectEvent"];
}) {
  const [limit, setLimit] = useState(20);
  return <>
    {rows.length === 0 && <p>No explicitly attributed timeline events in this window. Older files may omit regional attribution.</p>}
    <ul className="turn-changes-events">{rows.slice(0, limit).map(({ event, visibleTurn, canPin }, index) =>
      <li key={event.event_id ?? index}>
        <span>Turn {visibleTurn}: {event.description}</span>
        <div>{onSelectEvent && canPin && <button type="button" onClick={() => onSelectEvent(event)}>Inspect event</button>}
          <button type="button" onClick={() => onSeek(visibleTurn)}>View turn {visibleTurn}</button></div>
      </li>)}</ul>
    {rows.length > limit && <button type="button" onClick={() => setLimit(limit + 20)}>Show more events ({rows.length - limit} remaining)</button>}
  </>;
}

export function TurnChanges({ bundle, currentTurn, selectedRegion, selectedCivilization, onSeek, onSelectEvent }: Props) {
  const entities = useMemo(() => comparisonEntities(bundle, currentTurn), [bundle, currentTurn]);
  const turns = useMemo(() => comparisonTurns(bundle, currentTurn), [bundle, currentTurn]);
  const mapSelection: HistoryEntity | null = selectedRegion ? { kind: "region", name: selectedRegion }
    : selectedCivilization ? { kind: "civilization", name: selectedCivilization } : null;
  // Like the region inspector, retain the initial map target when event
  // inspection replaces the map selection; later map changes are explicit.
  const [chosen, setChosen] = useState<string | null>(() => mapSelection ? key(mapSelection) : null);
  const [fromChoice, setFrom] = useState<number | null>(null);
  const [toChoice, setTo] = useState<number | null>(null);
  const entity = entities.find((row) => key(row) === chosen)
    ?? entities.find((row) => mapSelection && key(row) === key(mapSelection)) ?? entities[0];
  const from = fromChoice !== null && turns.includes(fromChoice) ? fromChoice : turns[0];
  const to = toChoice !== null && turns.includes(toChoice) ? toChoice : turns[turns.length - 1];
  const before = entity && from !== undefined ? readEntityTurn(bundle, entity, from) : null;
  const after = entity && to !== undefined ? readEntityTurn(bundle, entity, to) : null;
  const valid = before !== null && after !== null && from <= to;
  const changes = valid ? compareReadings(before, after) : [];
  const largest = largestRelativeChanges(changes);
  const fromZero = changes.filter((row) => row.before === 0 && row.after !== null && row.after !== 0);
  const events = valid ? changeEvents(bundle, entity, from, to, currentTurn) : [];

  return <section className="turn-changes" aria-label="What changed">
    <h2>What changed?</h2>
    <p>Compare two recorded turns through the selected turn ({currentTurn}). Changing this comparison keeps your timeline position.</p>
    <div className="turn-changes-controls">
      <label>Civilization or region<select aria-label="Compare civilization or region" value={entity ? key(entity) : ""}
        onChange={(event) => setChosen(event.target.value)}>
        {entities.map((row) => <option key={key(row)} value={key(row)}>{row.kind === "civilization" ? "Civilization" : "Region"}: {row.name}</option>)}
      </select></label>
      <label>Earlier turn<select aria-label="Compare from turn" value={from ?? ""} onChange={(event) => setFrom(Number(event.target.value))}>
        {turns.map((turn) => <option key={turn} value={turn}>{turn}</option>)}
      </select></label>
      <label>Later turn<select aria-label="Compare to turn" value={to ?? ""} onChange={(event) => setTo(Number(event.target.value))}>
        {turns.map((turn) => <option key={turn} value={turn}>{turn}</option>)}
      </select></label>
      {mapSelection && entities.some((row) => key(row) === key(mapSelection)) && key(entity) !== key(mapSelection)
        && <button type="button" onClick={() => setChosen(key(mapSelection))}>Use map selection: {mapSelection.name}</button>}
    </div>
    {!valid ? <p role="status" aria-label="Turn comparison status">Choose two recorded turns with the earlier one first. No values are inferred for missing turns.</p> : <>
      <p role="status" aria-label="Turn comparison status">Turn {from}: {before.status} · Turn {to}: {after.status}</p>
      {entity.kind === "region" && <p>Controller: {before.controller} → {after.controller}</p>}
      {largest.length > 0 && <div><h3>Largest relative changes</h3><ul>
        {largest.map((row) => <li key={row.id}>{row.label}: {signed(row.delta)} ({signed(row.percent)}%)</li>)}
      </ul></div>}
      {fromZero.length > 0 && <p>Changed from zero: {fromZero.map((row) => `${row.label} → ${format(row.after)}`).join("; ")}. Percentage change is undefined.</p>}
      <div className="turn-changes-table"><table aria-label="Changes between recorded turns">
        <thead><tr><th>Measure</th><th>Turn {from}</th><th>Turn {to}</th><th>Change</th></tr></thead>
        <tbody>{changes.map((row) => <tr key={row.id}><th scope="row">{row.label}{row.note && <small>{row.note}</small>}</th>
          <td>{format(row.before)}</td><td>{format(row.after)}</td><td>{signed(row.delta)}</td></tr>)}</tbody>
      </table></div>
      <p>Missing observations stay unknown. No final-world values or carried-forward records fill gaps. Relative changes compare each measure with its own earlier value; they do not rank importance.</p>
      <h3>Recorded events in this window</h3>
      <p>These events explicitly name this {entity.kind}. Turn T shows the state after simulation step T−1, so event links use that completed step. Sharing the time window does not establish a cause of any measured change. Inspecting an event keeps the selected turn; View turn deliberately moves it.</p>
      <RecordedEvents key={JSON.stringify([key(entity), from, to])} rows={events} onSeek={onSeek} onSelectEvent={onSelectEvent} />
    </>}
  </section>;
}
