import { useMemo, useState } from "react";
import type { Bundle } from "../types";
import type { HistoryEntity } from "../lib/historyComparison";
import { whereToLook } from "../lib/whereToLook";
import "./where-to-look.css";

export interface WhereToLookProps {
  bundle: Bundle;
  currentTurn: number;
  onInspectEntity: (entity: HistoryEntity) => void;
}
export function WhereToLook({ bundle, currentTurn, onInspectEntity }: WhereToLookProps) {
  const result = useMemo(() => whereToLook(bundle, currentTurn), [bundle, currentTurn]);
  return <section className="where-to-look" aria-label="Where should I look?">
    <h2>Where should I look?</h2>
    <p>Recorded conditions at selected turn {currentTurn}. These are inspection prompts, with no universal score, forecast or causal claim. Order follows recorded regions and civilizations.</p>
    <LookResults key={currentTurn} result={result} onInspectEntity={onInspectEntity} />
  </section>;
}
function LookResults({ result, onInspectEntity }: { result: ReturnType<typeof whereToLook>; onInspectEntity: WhereToLookProps["onInspectEntity"] }) {
  const [limit, setLimit] = useState(8);
  return <>
    <p role="status">{result.status}. Showing {Math.min(limit, result.items.length)} of {result.items.length}; repeated conditions for an entity are grouped.</p>
    <ul className="where-to-look-items">{result.items.slice(0, limit).map((item) => <li key={JSON.stringify(item.entity)}>
      <h3>{item.entity.name} <small>({item.entity.kind})</small></h3>
      {item.reasons.map((reason) => <div key={reason.kind} className="where-to-look-reason">
        <strong>{reason.kind}</strong><span>{reason.window}</span><p>{reason.values}</p><p>{reason.reason}</p>
      </div>)}
      <button type="button" onClick={() => onInspectEntity(item.entity)}>Inspect history: {item.entity.name}</button>
    </li>)}</ul>
    {result.items.length > limit && <button type="button" onClick={() => setLimit(limit + 8)}>Show more ({result.items.length - limit} remaining)</button>}
    {result.items.length === 0 && <p>No matching recorded conditions. Check observation coverage before interpreting this as a quiet turn.</p>}
    <details><summary>Observation coverage and thresholds</summary><ul>{result.coverage.map((line) => <li key={line}>{line}</li>)}</ul>
      <p>Food distress: ratio below 1. Sharp population change: at least 20% between the stated endpoints with a positive earlier count; a zero baseline has no percentage. All comparisons stop at the selected turn.</p>
    </details>
  </>;
}
