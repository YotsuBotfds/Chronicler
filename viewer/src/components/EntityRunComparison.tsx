import { useMemo, useState } from "react";
import type { CompletedRun } from "../lib/completedRunComparison";
import { compareEntityRuns, ENTITY_RUN_MEASURES, orderEntityRunRows, type EntityRunKind, type EntityRunMeasure } from "../lib/entityRunComparison";
import "./entity-run-comparison.css";

export interface EntityRunComparisonProps { left: CompletedRun; right: CompletedRun; turn: number }
const format = (value: number | null) => value === null ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const signed = (value: number | null) => value === null ? "Unknown" : `${value > 0 ? "+" : ""}${format(value)}`;

export function EntityRunComparison({ left, right, turn }: EntityRunComparisonProps) {
  const [kind, setKind] = useState<EntityRunKind>("civilization");
  const [measureChoice, setMeasure] = useState<EntityRunMeasure>("population");
  const [order, setOrder] = useState<"higher" | "lower" | "name">("higher");
  const measures = ENTITY_RUN_MEASURES.filter((item) => (item.kinds as readonly string[]).includes(kind));
  const measure = measures.some((item) => item.id === measureChoice) ? measureChoice : "population";
  const summary = useMemo(() => compareEntityRuns(left, right, turn, kind, measure), [left, right, turn, kind, measure]);
  const rows = useMemo(() => orderEntityRunRows(summary.rows, order), [summary.rows, order]);
  return <section className="entity-run-comparison" aria-label="Per-entity run comparison">
    <h3>Regional and civilization differences</h3>
    <p>Snapshot {turn}: right minus left, one chosen measure at a time. Controls keep the selected comparison turn.</p>
    <div className="entity-run-controls">
      <label>Entity kind<select aria-label="Entity comparison kind" value={kind} onChange={(event) => setKind(event.target.value as EntityRunKind)}>
        <option value="civilization">Civilizations</option><option value="region">Regions</option>
      </select></label>
      <label>Measure<select aria-label="Entity comparison measure" value={measure} onChange={(event) => setMeasure(event.target.value as EntityRunMeasure)}>
        {measures.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label>
      <label>Order<select aria-label="Entity comparison order" value={order} onChange={(event) => setOrder(event.target.value as typeof order)}>
        <option value="higher">Higher right-minus-left first</option><option value="lower">Lower right-minus-left first</option><option value="name">Entity name</option>
      </select></label>
    </div>
    <p>{summary.measureNote}</p>
    <p role="status">{summary.matching.mode === "checkpoint-index" ? "Recorded common-checkpoint index matching" : "Unique observed-name matching; identity unverified"}.
      {` ${summary.counts.numericPairs}/${summary.counts.entities} entities have a numeric difference; ${summary.counts.unknownDifferences} unknown.`}</p>
    <ul className="entity-run-warnings">{summary.matching.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
    <EntityTable key={`${turn}:${kind}:${measure}:${order}`} rows={rows} label={summary.measureLabel} />
    <details><summary>Entity matching and measure limits</summary><ul>{summary.limits.map((limit) => <li key={limit}>{limit}</li>)}</ul>
      <p>Values and source notes reuse the existing exact entity-turn readers. Food weights, regional model populations, public treasury and debt keep their recorded units and coverage; these measures are not added into a score.</p>
    </details>
  </section>;
}
function EntityTable({ rows, label }: { rows: ReturnType<typeof orderEntityRunRows>; label: string }) {
  const [limit, setLimit] = useState(20);
  return <>
    <p>Showing {Math.min(rows.length, limit)} of {rows.length} entities. Unknown differences follow recorded differences.</p>
    <div className="entity-run-table" role="region" aria-label={`Scrollable entity ${label} differences`} tabIndex={0}><table aria-label={`Entity ${label} differences`}>
      <thead><tr><th>Entity / matching</th><th>Left</th><th>Right</th><th>Right − left</th><th>Relative to left</th></tr></thead>
      <tbody>{rows.slice(0, limit).map((row) => <tr key={row.key}>
        <th scope="row">{row.name}{" "}<small>{row.matching === "checkpoint-index" ? "Checkpoint-existing index" : row.matching === "name-only" ? "Name-only; identity unverified" : row.matching === "ambiguous" ? "Ambiguous name" : "Unmatched identity"}</small>
          <small>World indices: left {row.left.index ?? "unknown"} / right {row.right.index ?? "unknown"}</small></th>
        <td>{format(row.left.value)}<small>{row.left.status}</small>{row.left.note && <small>{row.left.note}</small>}</td>
        <td>{format(row.right.value)}<small>{row.right.status}</small>{row.right.note && <small>{row.right.note}</small>}</td>
        <td>{signed(row.delta)}</td><td>{row.percent === null ? "Unknown / undefined" : `${signed(row.percent)}%`}</td>
      </tr>)}</tbody>
    </table></div>
    {rows.length === 0 && <p>No entities have an unambiguous observation through this turn. No future entity list is inferred.</p>}
    {rows.length > limit && <button type="button" onClick={() => setLimit(limit + 20)}>Show more entities ({rows.length - limit} remaining)</button>}
  </>;
}
