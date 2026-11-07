import { useId, useMemo, useState } from "react";
import type { SystemPanelProps } from "../../lib/systems";
import { entityHistory, entityKey, entityLabel, indexEntityHistory, type EntityRef, type HistoryState } from "../../lib/entityHistory";

const LABELS: Record<HistoryState, string> = {
  disabled: "Off or unrecorded", unknown: "Unknown, not zero", malformed: "Rejected as malformed",
  not_sampled: "Not in sample", truncated: "Truncated evidence", recorded_zero: "Recorded: none", recorded: "Recorded",
};
const PAGE = 24;
/** Saved observations only: stable-id links and regional context stay visibly distinct. */
export function EntityHistory({ bundle, currentTurn, onSeek, onSelectRegion }: SystemPanelProps) {
  const index = useMemo(() => indexEntityHistory(bundle), [bundle]);
  const [selected, setSelected] = useState<EntityRef | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const picker = useId();
  const available = useMemo(() => {
    const named = new Map<string, EntityRef>();
    for (const { snapshot, frames } of index.snapshots) if (snapshot.turn <= currentTurn)
      for (const frame of Object.values(frames)) for (const row of frame.rows)
        for (const item of [row.entity, ...row.related]) named.set(entityKey(item), item);
    return [...named.values()].sort((a, b) => a.kind.localeCompare(b.kind) || String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
  }, [index, currentTurn]);
  const entity = selected && available.some((e) => entityKey(e) === entityKey(selected)) ? selected : available.find((e) => e.kind === "person") ?? available[0];
  const rows = useMemo(() => entity ? entityHistory(index, entity, currentTurn) : [], [index, entity, currentTurn]);
  if (!entity) return null;
  const choose = (next: EntityRef) => { setSelected(next); setLimit(PAGE); };
  return <section className="systems-section" aria-label="Linked histories">
    <h3>Linked histories</h3>
    <p className="systems-note">Saved completed-turn observations joined by stable id. These links show participation and co-occurrence, not causation. Regional totals are context and are never assigned to a person. Gaps are not interpolated; an absent id does not prove death, migration, or inactivity outside the named frame. Pool rebuilds cannot establish continuity of a person across an inexact resume.</p>
    <label htmlFor={picker}>Recorded entity</label>{" "}
    <select id={picker} value={entityKey(entity)} onChange={(e) => {
      const next = available.find((item) => entityKey(item) === e.target.value);
      if (next) choose(next);
    }}>{available.map((e) => <option key={entityKey(e)} value={entityKey(e)}>{entityLabel(e)}</option>)}</select>
    <p className="systems-note">{entityLabel(entity)} through snapshot {currentTurn}. Only entities actually named in accepted records are listed. Person purchase amounts, individual shares of crew totals, and unrecorded residences remain unknown.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Linked history of ${entityLabel(entity)}`}>
      <thead><tr><th>Snapshot / source turn</th><th>Observation</th><th>Join / state</th><th>Related records</th><th>Bundle source</th></tr></thead>
      <tbody>{rows.slice(-limit).map((row, i) => <tr key={`${row.turn}:${row.package}:${row.source}:${i}`}>
        <td><button type="button" className="systems-link" onClick={() => onSeek(row.turn)}>Snapshot {row.turn}</button><br/>Source turn {row.sourceTurn ?? "unknown"}</td>
        <td><strong>{row.package.replace(/_/g, " ")}</strong><br/>{row.text}</td>
        <td>{row.join === "region" ? "Region only" : row.join === "inferred" ? "Inferred by named rule" : "Stable id"}<br/>{LABELS[row.state]}</td>
        <td>{row.related.map((related) => <button key={entityKey(related)} type="button" className="systems-link" onClick={() => choose(related)}>{entityLabel(related)} </button>)}
          {row.region !== null ? <button type="button" className="systems-link" onClick={() => onSelectRegion(bundle.world_state.regions[row.region!]?.name ?? "")}>Open {bundle.world_state.regions[row.region]?.name ?? `region ${row.region}`}</button> : null}</td>
        <td>{row.source ? <code style={{ overflowWrap: "anywhere" }}>{row.source}</code> : "No recorded source"}</td>
      </tr>)}</tbody>
    </table></div>
    {!rows.length ? <p className="systems-note">No observations at or before this snapshot.</p> : null}
    {rows.length > limit ? <button type="button" onClick={() => setLimit((n) => n + PAGE)}>Show earlier observations ({rows.length - limit} more)</button> : null}
  </section>;
}
