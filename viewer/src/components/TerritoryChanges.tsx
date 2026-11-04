import { useMemo, useState } from "react";
import type { Bundle } from "../types";
import type { HistoryEntity } from "../lib/historyComparison";
import { compareTerritory, territoryEarlierTurns, TERRITORY_LABELS, type TerritoryComparison, type TerritoryStatus } from "../lib/territoryChanges";
import "./territory-changes.css";

export interface TerritoryChangesProps {
  bundle: Bundle;
  currentTurn: number;
  selectedRegion?: string | null;
  selectedCivilization?: string | null;
  onInspectEntity: (entity: HistoryEntity) => void;
  onSeek?: (turn: number) => void;
  /** Optional map synchronization; changing comparison never seeks. */
  onComparisonChange?: (fromTurn: number | null, civilizationIndex: number | null) => void;
}

const uniqueCivs = (bundle: Bundle, through: number) => bundle.world_state.civilizations.flatMap((civ, index, all) =>
  all.filter((row) => row.name === civ.name).length === 1
    && bundle.history.some((row) => row.turn <= through && Object.hasOwn(row.civ_stats, civ.name)) ? [{ name: civ.name, index }] : []);

export function TerritoryChanges(props: TerritoryChangesProps) {
  // Bounded selection state resets when the timeline changes.
  return <TerritoryControls key={props.currentTurn} {...props} />;
}
function TerritoryControls({ bundle, currentTurn, selectedRegion, selectedCivilization, onInspectEntity, onSeek, onComparisonChange }: TerritoryChangesProps) {
  const turns = useMemo(() => territoryEarlierTurns(bundle, currentTurn), [bundle, currentTurn]);
  const civilizations = useMemo(() => uniqueCivs(bundle, currentTurn), [bundle, currentTurn]);
  const mapCiv = civilizations.find((civ) => civ.name === selectedCivilization)?.index ?? null;
  const [fromChoice, setFrom] = useState<number | null>(null);
  const [focusChoice, setFocus] = useState<number | null>(mapCiv);
  const [scope, setScope] = useState<TerritoryStatus | "all" | "changed">("all");
  const from = fromChoice !== null && turns.includes(fromChoice) ? fromChoice : turns.at(-1) ?? null;
  const focus = civilizations.some((civ) => civ.index === focusChoice) ? focusChoice : null;
  const comparison = useMemo(() => compareTerritory(bundle, currentTurn, from, focus), [bundle, currentTurn, from, focus]);
  const update = (nextFrom: number | null, nextFocus: number | null) => {
    setFrom(nextFrom); setFocus(nextFocus); onComparisonChange?.(nextFrom, nextFocus);
  };
  const statuses: TerritoryStatus[] = focus === null ? ["gained", "lost", "transferred", "unchanged", "unknown"]
    : ["gained", "lost", "unchanged", "outside", "unknown"];
  return <section className="territory-changes" aria-label="Territory changes">
    <h2>Territory changes</h2>
    <p>Compare an earlier recorded turn with selected turn {currentTurn}. Controls and history inspection keep your timeline position.</p>
    <div className="territory-controls">
      <label>Earlier turn<select aria-label="Territory earlier turn" value={from ?? ""} onChange={(event) => update(Number(event.target.value), focus)}>
        {turns.length === 0 && <option value="">No earlier record</option>}
        {turns.map((turn) => <option key={turn} value={turn}>{turn}</option>)}
      </select></label>
      <label>Civilization focus<select aria-label="Territory civilization focus" value={focus ?? "all"}
        onChange={(event) => update(from, event.target.value === "all" ? null : Number(event.target.value))}>
        <option value="all">All controllers</option>
        {civilizations.map((civ) => <option key={civ.index} value={civ.index}>{civ.name}</option>)}
      </select></label>
      <label>Regions shown<select aria-label="Territory region scope" value={statuses.includes(scope as TerritoryStatus) || scope === "all" || scope === "changed" ? scope : "all"}
        onChange={(event) => setScope(event.target.value as typeof scope)}>
        <option value="all">All regions</option><option value="changed">Changed ownership</option>
        {statuses.map((status) => <option key={status} value={status}>{TERRITORY_LABELS[status]}</option>)}
      </select></label>
      {mapCiv !== null && mapCiv !== focus && <button type="button" onClick={() => update(from, mapCiv)}>Use map civilization: {selectedCivilization}</button>}
    </div>
    <p role="status">{comparison.status}. {comparison.fromTurn !== null && <>T{comparison.fromTurn} → T{currentTurn}.</>}</p>
    <p>{statuses.map((status) => `${TERRITORY_LABELS[status]}: ${comparison.counts[status]}`).join(" · ")}</p>
    {focus === null && <p>Gained: uncontrolled to a known civilization. Lost: known civilization to uncontrolled. Transferred: between two known civilization identities.</p>}
    <TerritoryRows key={JSON.stringify([from, focus, scope])} comparison={comparison}
      scope={statuses.includes(scope as TerritoryStatus) || scope === "all" || scope === "changed" ? scope : "all"}
      selectedRegion={selectedRegion} onInspectEntity={onInspectEntity} />
    {onSeek && comparison.valid && <div className="territory-actions">
      <button type="button" onClick={() => onSeek(comparison.fromTurn!)}>View turn {comparison.fromTurn}</button>
      <button type="button" onClick={() => onSeek(currentTurn)}>View turn {currentTurn}</button>
    </div>}
    <p>Ownership is compared only at exact endpoints. Missing or ambiguous region names, controllers or civilization identities stay unknown. Region names are matched only when unambiguous; historical aliases are not invented. A recorded transfer does not establish conquest or its cause.</p>
  </section>;
}
function TerritoryRows({ comparison, scope, selectedRegion, onInspectEntity }: {
  comparison: TerritoryComparison; scope: TerritoryStatus | "all" | "changed";
  selectedRegion?: string | null; onInspectEntity: TerritoryChangesProps["onInspectEntity"];
}) {
  const [limit, setLimit] = useState(20);
  const rows = comparison.rows.filter((row) => scope === "all" || (scope === "changed"
    ? ["gained", "lost", "transferred"].includes(row.status) : row.status === scope));
  return <>
    <p>Showing {Math.min(limit, rows.length)} of {rows.length} matching regions.</p>
    <div className="territory-table"><table aria-label="Regional ownership changes">
      <thead><tr><th>Region</th><th>Earlier controller</th><th>Selected controller</th><th>Change</th><th>History</th></tr></thead>
      <tbody>{rows.slice(0, limit).map((row) => <tr key={row.regionId} aria-current={row.name === selectedRegion ? "true" : undefined}>
        <th scope="row">{row.name}</th><td>{row.before.label}{row.before.reason && <small>{row.before.reason}</small>}</td>
        <td>{row.after.label}{row.after.reason && <small>{row.after.reason}</small>}</td><td>{TERRITORY_LABELS[row.status]}</td>
        <td>{row.inspectable ? <button type="button" onClick={() => onInspectEntity({ kind: "region", name: row.name })}>Inspect history: {row.name}</button> : "Ambiguous region name"}</td>
      </tr>)}</tbody>
    </table></div>
    {rows.length === 0 && <p>No matching regions. Unknown observations are counted separately.</p>}
    {rows.length > limit && <button type="button" onClick={() => setLimit(limit + 20)}>Show more regions ({rows.length - limit} remaining)</button>}
  </>;
}
