import { useId, useLayoutEffect, useRef, useState } from "react";
import {
  inspectSettlementHistory, isSettlementId, settlementOptions, settlementPopulationHistory,
  type RecordedSettlementValue, type SettlementSnapshot,
} from "../../lib/settlementInspection";

interface Props {
  history: readonly SettlementSnapshot[];
  requestedTurn: number;
  settlementId: number | null;
  onSelectSettlement: (id: number | null) => void;
  onSeek?: (turn: number) => void;
  onClose?: () => void;
}

const PAGE_SIZE = 20;
const turnLabel = (value: number) => Number.isSafeInteger(value) && value >= 0 ? String(value) : "unavailable";

function Value({ label, observation }: { label: string; observation: RecordedSettlementValue<string | number> }) {
  return <div><dt>{label}</dt><dd>{observation.value ?? `Unavailable — ${observation.unavailable}`}</dd></div>;
}

function PopulationSamples({ history, requestedTurn, settlementId, onSeek }: Omit<Props, "onSelectSettlement" | "onClose">) {
  const [page, setPage] = useState(0);
  const rows = settlementPopulationHistory(history, requestedTurn, settlementId);
  const visiblePage = Math.min(page, Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1));
  const previousButton = useRef<HTMLButtonElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const pendingFocus = useRef<"previous" | "next" | null>(null);
  useLayoutEffect(() => {
    if (pendingFocus.current) {
      (pendingFocus.current === "previous" ? previousButton : nextButton).current?.focus();
      pendingFocus.current = null;
    }
  }, [visiblePage]);
  return <>
    <p className="phase75-detail-copy">Recorded population samples through turn {turnLabel(requestedTurn)}, in source order. Gaps have no measured value. No growth curve is interpolated.</p>
    <div style={{ overflowX: "auto" }}>
      <table aria-label="Settlement population observations" style={{ width: "100%", textAlign: "left" }}>
        <thead><tr><th scope="col">History turn</th><th scope="col">Population estimate</th><th scope="col">Source turn</th></tr></thead>
        <tbody>{rows.slice(visiblePage * PAGE_SIZE, (visiblePage + 1) * PAGE_SIZE).map(({ turn, inspection }, index) => <tr key={visiblePage * PAGE_SIZE + index}>
          <td>{onSeek ? <button type="button" onClick={() => onSeek(turn)} aria-label={`Inspect settlement at turn ${turn}`}>{turn}</button> : turn}</td>
          <td>{inspection.summary?.population.value ?? (inspection.state === "dissolved" ? "Recorded dissolution"
            : inspection.state === "not-listed" ? "Not listed" : "Unavailable")}</td>
          <td>{inspection.sourceTurn.value ?? "Unavailable"}{inspection.freshness === "stale" ? ` · ${inspection.observationAge} turns old` : ""}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p>{rows.length === 0 ? "No timestamped historical samples in this window."
      : `${visiblePage * PAGE_SIZE + 1}–${Math.min((visiblePage + 1) * PAGE_SIZE, rows.length)} of ${rows.length} historical samples`}</p>
    <div className="phase75-stat-row">
      <button ref={previousButton} type="button" disabled={visiblePage === 0} onClick={event => {
        if (visiblePage === 1 && document.activeElement === event.currentTarget) pendingFocus.current = "next";
        setPage(visiblePage - 1);
      }}>Previous samples</button>
      <button ref={nextButton} type="button" disabled={(visiblePage + 1) * PAGE_SIZE >= rows.length} onClick={event => {
        if ((visiblePage + 2) * PAGE_SIZE >= rows.length && document.activeElement === event.currentTarget) pendingFocus.current = "previous";
        setPage(visiblePage + 1);
      }}>Next samples</button>
    </div>
  </>;
}

/** Controlled selection/turn, ready for later mounting behind the Phase 7.5 gates. */
export function SettlementInspector({ history, requestedTurn, settlementId, onSelectSettlement, onSeek, onClose }: Props) {
  const labelId = useId();
  const inspection = inspectSettlementHistory(history, requestedTurn, settlementId);
  const options = settlementOptions(history, requestedTurn);
  const summary = inspection.summary;
  const freshness = inspection.freshness === "unavailable"
    ? "Observation age unavailable; settlement source timestamp is missing or unusable."
    : `${inspection.freshness === "stale" ? "Stale summary" : "Same-turn source timestamp"} · source turn ${inspection.sourceTurn.value} · observation age ${inspection.observationAge} turns.`;
  return <section className="phase75-panel" aria-labelledby={labelId}>
    <header className="phase75-inspector-header">
      <div className="phase75-overline">Historical settlement · as of turn {turnLabel(requestedTurn)}</div>
      <h3 id={labelId}>{summary?.name.value ?? (settlementId === null ? "Settlement inspector" : `Settlement #${settlementId}`)}</h3>
      {onClose && <button type="button" onClick={onClose}>Close settlement inspector</button>}
      <label className="phase75-field"><span>Settlement</span>
        <select value={isSettlementId(settlementId) ? settlementId : ""} onChange={(event) => onSelectSettlement(event.target.value === "" ? null : Number(event.target.value))}>
          <option value="">Choose a settlement</option>
          {isSettlementId(settlementId) && !options.some((option) => option.id === settlementId) && <option value={settlementId}>Settlement #{settlementId} · selected ID</option>}
          {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select>
      </label>
      <p role="status" aria-live="polite" aria-atomic="true">As of turn {turnLabel(requestedTurn)}. {inspection.explanation} {freshness}</p>
      <p className="phase75-detail-copy">The source timestamp does not establish when detection last ran or when each value last changed.</p>
    </header>
    <div className="phase75-section-body">
      {summary && <dl className="phase75-mini-card" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(145px, 1fr))", gap: 12 }}>
        <Value label="Region" observation={summary.region} />
        <Value label="Status" observation={summary.status} />
        <Value label="Population estimate" observation={summary.population} />
        <Value label="Founding turn" observation={summary.foundingTurn} />
        <Value label="Centroid X" observation={summary.centroidX} />
        <Value label="Centroid Y" observation={summary.centroidY} />
      </dl>}
      <div className="phase75-mini-card">
        <h4>Lifecycle in this snapshot</h4>
        <p>Founding: {inspection.founded.value === null ? `Unavailable — ${inspection.founded.unavailable}`
          : inspection.founded.value ? "Recorded in this snapshot" : "Not listed in this snapshot"}</p>
        <p>Dissolution: {inspection.dissolved.value === null ? `Unavailable — ${inspection.dissolved.unavailable}`
          : inspection.dissolved.value ? "Recorded in this snapshot" : "Not listed in this snapshot"}</p>
      </div>
      <details className="phase75-mini-card"><summary>Recorded population history</summary>
        <PopulationSamples key={JSON.stringify([requestedTurn, settlementId])} history={history} requestedTurn={requestedTurn}
          settlementId={settlementId} onSeek={onSeek} />
      </details>
      <details className="phase75-mini-card"><summary>Source provenance</summary>
        <p>JSON pointers refer to the supplied historical snapshots.</p>
        <ul style={{ overflowWrap: "anywhere" }}>
          <li>Summary / availability: <code>{inspection.source}</code></li>
          <li>Source timestamp: <code>{inspection.sourceTurn.source}</code> · {inspection.sourceTurn.value ?? inspection.sourceTurn.unavailable}</li>
          <li>Founding list: <code>{inspection.founded.source}</code></li>
          <li>Dissolution list: <code>{inspection.dissolved.source}</code></li>
          {summary && Object.entries(summary).map(([field, observation]) => <li key={field}>{field}: <code>{observation.source}</code></li>)}
        </ul>
      </details>
      <div className="phase75-empty-state"><h4>Additional settlement details unavailable</h4>
        <p className="phase75-detail-copy">Infrastructure, pull factors, notable residents, peak population, and last detection time are not exported in these historical summaries.</p>
      </div>
    </div>
  </section>;
}
