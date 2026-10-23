import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Bundle } from "../types";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import {
  inspectRegionEvents, inspectRegionHistory, recordedTurnBounds, regionMetrics, regionNames,
  type RegionHistoryEvent, type RegionHistoryRow,
} from "../lib/regionHistory";
import "./region-history.css";

interface Props {
  bundle: Bundle;
  artifactIdentity?: ArtifactIdentity | null;
  selectedRegion?: string | null;
  currentTurn: number;
  onSeek: (turn: number) => void;
}

const PAGE_SIZE = 50;

function Results({ rows, events, currentTurn, onSeek, maxTurn }: {
  rows: RegionHistoryRow[]; events: RegionHistoryEvent[]; currentTurn: number;
  onSeek: (turn: number) => void; maxTurn: number;
}) {
  const [rowPage, setRowPage] = useState(0);
  const [eventPage, setEventPage] = useState(0);
  const turnLink = (turn: number) => turn >= 1 && turn <= maxTurn
    ? <button type="button" onClick={() => onSeek(turn)} aria-label={`Inspect turn ${turn}`}>{turn}</button>
    : <span title="Outside the main timeline's navigable range">{turn}</span>;
  const pages = (count: number, page: number, setPage: (page: number) => void, kind: string) => (
    <div className="region-history-pages">
      <span>{count === 0 ? `No ${kind} in this window.`
        : `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, count)} of ${count} ${kind}`}</span>
      <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label={`Previous ${kind}`}>Previous</button>
      <button type="button" disabled={(page + 1) * PAGE_SIZE >= count} onClick={() => setPage(page + 1)} aria-label={`Next ${kind}`}>Next</button>
    </div>
  );
  return <>
    <div className="region-history-table">
      <table aria-label="Region metric observations">
        <thead><tr><th>Turn</th><th>Controller</th><th>Value / availability</th><th>Source (JSON pointer)</th></tr></thead>
        <tbody>{rows.slice(rowPage * PAGE_SIZE, (rowPage + 1) * PAGE_SIZE).map((row, index) => (
          <tr key={`${row.source}-${index}`} aria-current={row.turn === currentTurn ? "true" : undefined}>
            <td>{turnLink(row.turn)}</td>
            <td>{row.controller === undefined ? "Controller not recorded" : row.controller === null ? "Uncontrolled" : row.controller}</td>
            <td>{row.value === null ? row.missing : String(row.value)}</td>
            <td><code>{row.source}</code></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
    {pages(rows.length, rowPage, setRowPage, "observations")}
    <h3>Events in this window</h3>
    <p>Recorded-region events use the explicit named-event region. Optional controller context matches actors to the controller recorded at that exact turn; it does not establish where an event happened or what caused a metric change. Agent-event sidecars are not loaded here.</p>
    <div className="region-history-table">
      <table aria-label="Region history events">
        <thead><tr><th>Turn</th><th>Type / scope</th><th>Description</th><th>Source (JSON pointer)</th></tr></thead>
        <tbody>{events.slice(eventPage * PAGE_SIZE, (eventPage + 1) * PAGE_SIZE).map((event) => (
          <tr key={event.source}><td>{turnLink(event.turn)}</td>
            <td>{event.type}<br /><small>{event.scope}</small></td><td>{event.description}</td><td><code>{event.source}</code></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
    {pages(events.length, eventPage, setEventPage, "events")}
  </>;
}

export function RegionHistoryInspector({ bundle, artifactIdentity, selectedRegion, currentTurn, onSeek }: Props) {
  const names = useMemo(() => regionNames(bundle), [bundle]);
  const metrics = useMemo(() => regionMetrics(bundle), [bundle]);
  const [first, last] = useMemo(() => recordedTurnBounds(bundle), [bundle]);
  const [region, setRegion] = useState(selectedRegion ?? names[0] ?? "");
  const [metricId, setMetricId] = useState("ecology:soil");
  const [startText, setStart] = useState(String(first));
  const [endText, setEnd] = useState(String(last));
  const [eventType, setEventType] = useState("");
  const [context, setContext] = useState(false);
  const start = Number(startText);
  const end = Number(endText);
  const validRange = startText.trim() !== "" && endText.trim() !== "" && Number.isSafeInteger(start)
    && Number.isSafeInteger(end) && start >= first && end <= last && start <= end;
  const metric = metrics.find((candidate) => candidate.id === metricId) ?? metrics[0];
  const inspection = useMemo(() => validRange ? inspectRegionHistory(bundle, region, metric, start, end)
    : { rows: [], unrecordedTurns: 0 }, [bundle, region, metric, start, end, validRange]);
  const events = useMemo(() => validRange ? inspectRegionEvents(bundle, region, start, end, eventType, context)
    : [], [bundle, region, start, end, eventType, context, validRange]);
  const eventTypes = useMemo(() => [...new Set([...bundle.named_events, ...bundle.events_timeline]
    .map((event) => event.event_type))].sort(), [bundle]);
  const observed = inspection.rows.filter((row) => row.value !== null).length;

  return <section className="region-history" aria-label="Region history inspector">
    <h2>Region history</h2>
    <p>Inspect exported observations without interpolation. Ecology values are raw fractions; stockpiles show each named good in its exported units. No food aggregate is computed.</p>
    <div className="region-history-provenance">
      <span>Run: {bundle.world_state.name} · seed {bundle.metadata.seed} · bundle version {bundle.metadata.bundle_version ?? "unrecorded"} · generated {bundle.metadata.generated_at || "unrecorded"}</span>
      {artifactIdentity ? <>
        <span>Raw artifact: {artifactIdentity.name} · {artifactIdentity.byteLength} bytes</span>
        <code>SHA-256: {artifactIdentity.sha256 ?? "Unavailable (Web Crypto unavailable)"}</code>
      </> : <span>Raw artifact identity unavailable for in-memory data. Run metadata is not a content identity.</span>}
    </div>
    <div className="region-history-controls">
      <label>Region<select aria-label="Region" value={region} onChange={(event) => setRegion(event.target.value)}>
        {names.map((name) => <option key={name}>{name}</option>)}
      </select></label>
      {selectedRegion && names.includes(selectedRegion) && selectedRegion !== region &&
        <button type="button" onClick={() => setRegion(selectedRegion)}>Use map selection: {selectedRegion}</button>}
      <label>Metric<select aria-label="Metric" value={metricId} onChange={(event) => setMetricId(event.target.value)}>
        {metrics.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.label}</option>)}
      </select></label>
      <label>From turn<input type="number" min={first} max={last} step="1" value={startText} onChange={(event) => setStart(event.target.value)} /></label>
      <label>Through turn<input type="number" min={first} max={last} step="1" value={endText} onChange={(event) => setEnd(event.target.value)} /></label>
      <label>Event type<select aria-label="Event type" value={eventType} onChange={(event) => setEventType(event.target.value)}>
        <option value="">All types</option>{eventTypes.map((type) => <option key={type}>{type}</option>)}
      </select></label>
      <label className="region-history-checkbox"><input type="checkbox" checked={context} onChange={(event) => setContext(event.target.checked)} />Include controller event context</label>
    </div>
    {!validRange ? <p role="alert">Choose whole turns from {first} through {last}, with the start at or before the end.</p> : <>
      <p role="status">{observed} recorded values · {inspection.rows.length - observed} missing values · {inspection.unrecordedTurns} turns without observations in this inclusive window. Missing values are not zero.</p>
      {metric.kind === "stockpile" && <p>Historical stockpiles are not exported. The final-state observation at turn {bundle.world_state.turn} is shown separately, even when a history snapshot has the same turn. Salt remains a separate good.</p>}
      {metric.kind === "ecology" && observed > 0 && <div className="region-history-chart" aria-label={`${metric.label} by recorded turn`}>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={inspection.rows}>
            <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
            <XAxis dataKey="turn" type="number" domain={[start, end]} />
            <YAxis /><Tooltip />
            <Line dataKey="value" name={metric.label} stroke="#7ebec3" strokeWidth={0}
              dot={{ r: 3, fill: "#7ebec3" }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <p>Dots show recorded samples; missing and unsampled turns have no measured value. Consult the table for exact values and source paths.</p>
      </div>}
      <Results key={JSON.stringify([region, metric.id, start, end, eventType, context])}
        rows={inspection.rows} events={events} currentTurn={currentTurn} onSeek={onSeek} maxTurn={bundle.metadata.total_turns} />
    </>}
  </section>;
}
