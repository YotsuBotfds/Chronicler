import { useMemo, useState } from "react";
import type { Bundle, Event } from "../types";
import { interestingPeriods, PERIOD_TYPES } from "../lib/investigation";
import "./investigation.css";

export function InterestingPeriods({ bundle, currentTurn, onSeek, onEvent }: {
  bundle: Bundle; currentTurn: number; onSeek: (turn: number) => void; onEvent: (event: Event) => void;
}) {
  const [open, setOpen] = useState(false);
  const periods = useMemo(() => open ? interestingPeriods(bundle, currentTurn) : [], [bundle, currentTurn, open]);
  const [limit, setLimit] = useState(8);
  return <details className="interesting-periods" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Find recorded periods · through turn {currentTurn}</summary>
    <p>At least two qualifying event reports in a fixed five-turn window. Exact duplicates count once; conflicting reports remain separate. This groups activity, not severity or causation. Only the exported event timeline through this selected turn is inspected.</p>
    <details><summary>Selection rule and event types</summary><p>{Object.entries(PERIOD_TYPES).map(([kind, category]) => `${kind} (${category})`).join(", ")}. Snapshot T follows tick T−1; missing events/history are unknown.</p></details>
    {periods.length === 0 && <p>No matching periods through this turn. Choose a later available turn to inspect more recorded history.</p>}
    {periods.slice(0, limit).map((period) => <section key={period.start} aria-label={`Recorded period ${period.start}–${period.end}`}>
      <h3>Turns {period.start}–{period.end} · {period.categories.join("; ")}</h3>
      <button type="button" onClick={() => onSeek(period.events[0].snapshotTurn)}>View first recorded turn {period.events[0].snapshotTurn}</button>
      <PeriodReports key={`${period.start}:${currentTurn}`} rows={period.events} onEvent={onEvent} />
    </section>)}
    {periods.length > limit && <button type="button" onClick={() => setLimit(limit + 8)}>Show more periods</button>}
  </details>;
}

function PeriodReports({ rows, onEvent }: { rows: import("../lib/investigation").EvidenceEvent[]; onEvent: (event: Event) => void }) {
  const [limit, setLimit] = useState(50);
  return <details><summary>Inspect all {rows.length} underlying reports</summary><ul>
    {rows.slice(0, limit).map((row) => <li key={row.source}>T{row.snapshotTurn} · {row.event.event_type}: {row.event.description}
      <code>{row.source}</code>{row.canPin && <button type="button" onClick={() => onEvent(row.event)}>Inspect event</button>}</li>)}
  </ul>{rows.length > limit && <button type="button" onClick={() => setLimit(limit + 50)}>Show more underlying reports</button>}</details>;
}
