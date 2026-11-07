import { useMemo } from "react";
import type { Bundle, Event } from "../types";
import { regionInvestigation } from "../lib/investigation";
import { requestEntityHistory } from "../lib/entityHistoryNavigation";
import "./investigation.css";

export function RegionInvestigation({ bundle, regionIndex, currentTurn, onHistory, onCivilization, onEvent }: {
  bundle: Bundle; regionIndex: number; currentTurn: number; onHistory: () => void;
  onCivilization: (name: string) => void; onEvent: (event: Event) => void;
}) {
  const context = useMemo(() => regionInvestigation(bundle, regionIndex, currentTurn), [bundle, regionIndex, currentTurn]);
  if (!context) return null;
  return <section className="region-investigation" aria-label="Selected region investigation">
    <h3>Recorded conditions · turn {currentTurn}</h3>
    <p>Region identity {regionIndex}. {context.reading?.status ?? "Ambiguous region name; historical values unknown."}</p>
    <dl><dt>Political owner</dt><dd>{context.owner === undefined ? "Unknown" : context.owner === null ? "Uncontrolled" : context.owner}</dd>
      {context.reading?.metrics.filter((row) => ["population", "nativePopulation", "food", "grain"].includes(row.id)).map((row) =>
        <div key={row.id}><dt>{row.label}</dt><dd>{row.value === null ? "Unknown" : row.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd></div>)}
    </dl>
    {context.unique && <><button type="button" onClick={onHistory}>Inspect history: {context.name}</button><button type="button" onClick={()=>requestEntityHistory({kind:"region",id:regionIndex},currentTurn)}>Linked system history: {context.name}</button></>}
    {context.ownerIndex !== null && typeof context.owner === "string" && <button type="button" onClick={() => onCivilization(context.owner! as string)}>Inspect owner: {context.owner}</button>}
    <details><summary>Recent regional reports · turns {context.from}–{context.through}</summary>
      <p>Explicitly named region only. Controller-wide events are not assigned to its regions. Nearby events do not establish causes. Snapshot T follows simulation tick T−1.</p>
      {context.events.length + context.named.length === 0 && <p>No explicit regional reports in this window; this does not prove no events occurred.</p>}
      <ul>{context.events.map((row) => <li key={row.source}><strong>T{row.snapshotTurn} · {row.event.event_type}</strong>
        <p>{row.event.description}</p><code>{row.source}</code>
        {row.canPin && <button type="button" onClick={() => onEvent(row.event)}>Inspect recorded event</button>}
      </li>)}{context.named.map((row) => <li key={row.source}><strong>T{row.snapshotTurn} · {row.event.name}</strong>
        <p>{row.event.description}</p><code>{row.source}</code></li>)}</ul>
    </details>
  </section>;
}
