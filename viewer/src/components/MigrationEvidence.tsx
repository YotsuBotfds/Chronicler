import { useMemo, useState } from "react";
import type { Bundle } from "../types";
import { readMigrationEvidence } from "../lib/migrationEvidence";
import "./migration-evidence.css";

interface MigrationEvidenceProps {
  bundle: Bundle;
  currentTurn: number;
  selectedRegionIndex?: number | null;
  onInspectRegion?: (regionIndex: number, regionName: string) => void;
}

const PAGE_SIZE = 8;

export function MigrationEvidence({ bundle, currentTurn, selectedRegionIndex, onInspectRegion }: MigrationEvidenceProps) {
  const reading = useMemo(() => readMigrationEvidence(bundle, currentTurn, selectedRegionIndex),
    [bundle, currentTurn, selectedRegionIndex]);
  const scope = `${currentTurn}:${selectedRegionIndex ?? "all"}`;
  const [page, setPage] = useState({ scope, limit: PAGE_SIZE });
  if (page.scope !== scope) setPage({ scope, limit: PAGE_SIZE });
  const limit = page.scope === scope ? page.limit : PAGE_SIZE;
  const regionLabel = (index: number, name: string) => onInspectRegion
    ? <button type="button" onClick={() => onInspectRegion(index, name)} aria-label={`Inspect region ${index}: ${name}`}>{name} (#{index})</button>
    : <span>{name} (#{index})</span>;
  const population = reading.populationChange;

  return (
    <section className="migration-evidence" aria-label="Migration evidence">
      <h3>Recorded migration</h3>
      <p>Snapshot {currentTurn} · completed tick {reading.completedTick} · source tick {reading.sourceTick}</p>
      <p role="status">{reading.note}</p>
      {reading.status === "recorded" && <>
        <p>
          Recorded moves{selectedRegionIndex == null ? "" : " involving this region"}: <strong>{reading.totalAgents} native agents</strong>.
          {reading.netAgents !== null && <> Net native agents: <strong>{reading.netAgents > 0 ? "+" : ""}{reading.netAgents}</strong> (arrivals minus departures).</>}
        </p>
        <p>Native flows measure agent movement, not net model population change. Forced displacement, births and deaths cannot be identified from these flows.</p>
        {reading.flows.length > 0 && <>
          <p>Showing {Math.min(limit, reading.flows.length)} of {reading.flows.length} recorded region pairs.</p>
          <ol className="migration-evidence-flows" aria-label="Recorded migration flows">
            {reading.flows.slice(0, limit).map((flow) => <li key={`${flow.fromIndex}>${flow.toIndex}`}>
              <div>{regionLabel(flow.fromIndex, flow.fromName)} <span aria-label="to">→</span> {regionLabel(flow.toIndex, flow.toName)}</div>
              <p><strong>{flow.agents} native agents</strong> · Reason: unknown (not allocated to this flow).</p>
              <details><summary>Flow sources ({flow.sourcePointers.length})</summary>
                <p>Indices refer to <code>/world_state/regions</code>. Each source is a recorded [origin index, destination index, native agents] triple; repeated pairs are summed.</p>
                <ul>{flow.sourcePointers.map((pointer) => <li key={pointer}><code>{pointer}</code></li>)}</ul>
              </details>
            </li>)}
          </ol>
          {limit < reading.flows.length && <button type="button" onClick={() => setPage({ scope, limit: limit + PAGE_SIZE })}>Show more flows ({reading.flows.length - limit} remaining)</button>}
        </>}
      </>}
      {reading.sourcePointer && <p className="migration-evidence-source">Flow field: <code>{reading.sourcePointer}</code></p>}

      {selectedRegionIndex != null && <details>
        <summary>Separate model population observation</summary>
        {population ? <>
          <p>Exact snapshots {currentTurn - 1} → {currentTurn}: model population {population.before} → {population.after}; change {population.delta > 0 ? "+" : ""}{population.delta}. No cause is assigned or residual population category inferred.</p>
          <p>Sources: {population.beforeSource} → {population.afterSource}; modes: {population.beforeMode} → {population.afterMode}.</p>
          <ul>{population.sourcePointers.map((pointer) => <li key={pointer}><code>{pointer}</code></li>)}</ul>
        </> : <p>Unknown: both exact consecutive regional model population observations are required. Gaps are not interpolated.</p>}
      </details>}

      <details className="migration-evidence-context">
        <summary>Separate recorded event context ({reading.context.length})</summary>
        <p>Reports from source tick {reading.sourceTick} only. A report's driver is a group-dominant utility term; it is not a reason assigned to each origin–destination flow.</p>
        {reading.context.length === 0 ? <p>No unambiguous regional migration report recorded for this tick and selection. This does not establish an absence of movement.</p>
          : <ul>{reading.context.slice(0, limit).map((context) => <li key={context.sourcePointer}>
            <p>{context.event.description}</p>
            <p>{context.event.event_type} · tick {context.event.turn} · {regionLabel(context.regionIndex, bundle.world_state.regions[context.regionIndex].name)}</p>
            <p>Recorded group driver: {context.event.driver || "unknown"}{context.dominantUtilityTerm ? ` (${context.dominantUtilityTerm})` : ""}. No allocation to individual flow pairs.</p>
            <code>{context.sourcePointer}</code>
          </li>)}</ul>}
        {limit < reading.context.length && <button type="button" onClick={() => setPage({ scope, limit: limit + PAGE_SIZE })}>Show more reports ({reading.context.length - limit} remaining)</button>}
      </details>
    </section>
  );
}
