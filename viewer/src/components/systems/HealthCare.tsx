import { useMemo } from "react";
import { healthCareSeries } from "../../lib/healthCare";
import { hasObservation, observationAt } from "../../lib/observedSystems";
import type { SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile } from "./SystemParts";

const show = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const COLORS: Record<string, string> = {
  "Active injuries": "#e8b84a", "New injuries": "#d9644a", Recoveries: "#5aa88f",
  "Farmer work lost": "#d9644a", "Household care work": "#5a8fd9",
};

/** Actual injuries and household care, distinct from the epidemic model. */
export function HealthCare({ bundle, snapshot, currentTurn, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const recorded = hasObservation(bundle.history, "health_care");
  const record = observationAt(snapshot, "health_care");
  const at = snapshot?.turn ?? currentTurn;
  const series = useMemo(() => healthCareSeries(bundle.history, at), [bundle.history, at]);
  if (!recorded) return null;
  if (!record) return <section className="systems-section" aria-label="Injury and household care">
    <h3>Injury and household care</h3>
    <p className="systems-note">No injury or household-care observation at turn {currentTurn}. Missing history is unknown.</p>
  </section>;
  return <section className="systems-section" aria-label="Injury and household care">
    <h3>Injury and household care · snapshot {at}</h3>
    <p className="systems-note">Recorded after simulation turn {record.source_turn}. This is the rural farmer injury and household-care model. Work is measured in fractional worker-turns; these values do not describe medical spending or disease prevalence.</p>
    <div className="systems-tiles">
      <StatTile label="Active injury episodes" value={record.episodes} />
      <StatTile label="New injuries" value={record.new_injuries} detail="this completed turn" />
      <StatTile label="Recovered episodes" value={record.recoveries} detail="this completed turn" />
      <StatTile label="Farmer work lost" value={show(record.impaired_work)} detail="worker-turns" />
      <StatTile label="Household care work" value={show(record.care_work)} detail="caregiver worker-turns" />
      <StatTile label="Care recipients" value={record.care_recipients} detail="this completed turn" />
    </div>
    <div className="systems-chart-pair">
      <CivLineChart data={series} civs={["Active injuries", "New injuries", "Recoveries"]}
        color={(name) => COLORS[name]} currentTurn={at} label="Injury episodes and recoveries" step />
      <CivLineChart data={series} civs={["Farmer work lost", "Household care work"]}
        color={(name) => COLORS[name]} currentTurn={at} label="Injury and household-care work over time" format={show} step />
    </div>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Injury and care at snapshot ${at}`}>
      <thead><tr><th>Region</th><th>Controller</th><th>Active injuries</th><th>New injuries</th><th>Recoveries</th><th>Farmer work lost</th><th>Care work</th><th>Care recipients</th></tr></thead>
      <tbody>{record.regions.map((row) => <tr key={row.region}>
        <td><button type="button" className="systems-link" onClick={() => onSelectRegion(row.region_name)}>{row.region_name}</button></td>
        <td>{row.civ_name ? <button type="button" className="systems-link" onClick={() => onSelectCivilization(row.civ_name!)}>{row.civ_name}</button> : "Nobody"}</td>
        <td>{row.episodes}</td><td>{row.new_injuries}</td><td>{row.recoveries}</td><td>{show(row.impaired_work)}</td><td>{show(row.care_work)}</td><td>{row.care_recipients}</td>
      </tr>)}</tbody>
    </table></div>
    {record.recovery_progress != null && <p className="systems-note">Recorded recovery progress: {show(record.recovery_progress)}
      {record.cared_recovery_progress != null ? `, including ${show(record.cared_recovery_progress)} among care recipients` : ""}.
      These are observed episode-progress totals, not an estimate of what care prevented.</p>}
    <p className="systems-note">History stops at this snapshot. Missing earlier observations remain gaps.</p>
  </section>;
}
