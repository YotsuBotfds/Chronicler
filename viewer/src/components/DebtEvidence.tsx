import { useMemo, useState } from "react";
import type { Bundle, Event } from "../types";
import { readDebtEvidence } from "../lib/debtEvidence";
import "./debt-evidence.css";

export interface DebtEvidenceProps {
  bundle: Bundle;
  currentTurn: number;
  civilizationIndex: number | null;
  window?: number;
  onInspectEvent?: (event: Event) => void;
  onViewRecordedTurn?: (turn: number) => void;
}
const show = (value: number | null) => value === null ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
export function DebtEvidence({ bundle, currentTurn, civilizationIndex, window, onInspectEvent, onViewRecordedTurn }: DebtEvidenceProps) {
  const [chosenWindow, setChosenWindow] = useState(20);
  const span = window ?? chosenWindow;
  const reading = useMemo(() => readDebtEvidence(bundle, currentTurn, civilizationIndex, span), [bundle, currentTurn, civilizationIndex, span]);
  return <section className="debt-evidence" aria-label="Debt payment evidence">
    <h3>Debt payment evidence</h3>
    <p>{reading.name} · selected snapshot {currentTurn}. Debt is boundary principal; flows below belong to the completed fiscal tick. Amounts use nominal treasury units.</p>
    <p role="status">{reading.status}</p>
    {window === undefined && <label className="debt-evidence-window">Snapshot window<select aria-label="Debt evidence window" value={chosenWindow} onChange={(event) => setChosenWindow(Number(event.target.value))}>
      <option value={10}>10-turn window</option><option value={20}>20-turn window</option><option value={50}>50-turn window</option>
    </select></label>}
    {reading.selected && <>
      <p>Total debt {show(reading.selected.values.debt)}; foreign subset {show(reading.selected.values.foreignDebt)}. The foreign subset is included in total debt.</p>
      <p>Fiscal borrowing can omit later-phase loans. Principal paid below is service minus paid interest, including prepayments; debt-stock changes are not used.</p>
      <div className="debt-evidence-table" role="region" aria-label="Scrollable fiscal payment ledger" tabIndex={0}><table aria-label={`Fiscal payment ledger for ${reading.name}`}>
        <caption>Snapshot window {reading.from}–{reading.through}. Unknown rows remain gaps. Defaults and write-offs are cumulative.</caption>
        <thead><tr><th>Snapshot / source tick</th><th>Debt / foreign subset</th><th>Fiscal borrowing</th><th>Debt service paid</th><th>Interest paid</th><th>Principal paid (service − interest)</th><th>Combined shortfall</th><th>Arrears turns</th><th>Defaults so far</th><th>Written off so far</th><th>Coverage / source</th></tr></thead>
        <tbody>{reading.rows.map((row) => <tr key={row.turn}>
          <th scope="row">{row.turn} / {row.sourceTurn ?? "opening"}{onViewRecordedTurn && row.status === "recorded" && row.turn !== currentTurn && <button type="button" onClick={() => onViewRecordedTurn(row.turn)}>View snapshot {row.turn}</button>}</th>
          <td>{show(row.values.debt)} / {show(row.values.foreignDebt)}</td><td>{show(row.values.borrowed)}</td><td>{show(row.values.service)}</td><td>{show(row.values.interestPaid)}</td><td>{show(row.values.principalPaid)}</td><td>{show(row.values.shortfall)}</td><td>{show(row.values.arrears)}</td><td>{show(row.values.defaults)}</td><td>{show(row.values.writtenOff)}</td>
          <td>{row.status}<details><summary>Observation basis</summary><p>{row.explanation}</p><code>{row.sourceRef}</code>{row.principalSources.map((source) => <code key={source}>{source}</code>)}{row.writtenOffSource && <code>{row.writtenOffSource}</code>}</details></td>
        </tr>)}</tbody>
      </table></div>
      <details><summary>Explicit named claims at the selected boundary ({reading.claims.length})</summary>
        <p>These are claim balances and rates, not receipts of paid interest. Unnamed claims and payment allocations remain unknown; existing debt-holder views show aggregate categories.</p>
        {reading.claims.length === 0 ? <p>No explicit named claim rows at this selected boundary. This does not establish that there are no creditors.</p> : <ul>{reading.claims.map((claim) => <li key={claim.sourceRef}>{claim.label} ({claim.kind}): principal {show(claim.principal)}; boundary rate {claim.rate === null ? "unknown" : `${show(claim.rate * 100)}% per turn`}<code>{claim.sourceRef}</code>{claim.rateSourceRef && <code>{claim.rateSourceRef}</code>}</li>)}</ul>}
      </details>
      <h4>Recorded credit events in this window</h4>
      <p>Borrower and named-creditor roles come from event actors. Event text is not parsed into amounts or used to allocate payments.</p>
      {reading.events.length === 0 && <p>No attributed credit events recorded in this window; this does not establish zero borrowing or payments.</p>}
      <ol className="debt-evidence-events">{reading.events.slice(-40).map((item) => <li key={item.sourceRef}>
        <strong>Snapshot {item.turn} (source tick {item.event.turn}) · {item.role}</strong>
        {item.borrower && <p>Borrower: {item.borrower}</p>}<p>{item.event.description}</p>
        {onInspectEvent && item.canInspect && <button type="button" onClick={() => onInspectEvent(item.event)}>Inspect credit event: {item.event.event_type}</button>}
        {!item.canInspect && <p>Event identity is ambiguous; inspection link unavailable.</p>}
        <details><summary>Event source</summary><code>{item.sourceRef}</code></details>
      </li>)}</ol>
      {reading.events.length > 40 && <p>Showing the most recent 40 of {reading.events.length} recorded events. Narrow the snapshot window for earlier detail.</p>}
      <details><summary>Debt evidence scope and limits</summary><ul>{reading.coverage.map((line) => <li key={line}>{line}</li>)}</ul></details>
    </>}
  </section>;
}
