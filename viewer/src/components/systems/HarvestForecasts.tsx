import { useMemo } from "react";
import { forecastTotals, harvestForecastSeries } from "../../lib/harvestForecasts";
import { hasObservation, observationAt } from "../../lib/observedSystems";
import type { SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile } from "./SystemParts";

const show = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const percent = (value: number) => `${show(value * 100)}%`;
const COLORS: Record<string, string> = { Pending: "#7d8a96", Delivered: "#5aa88f", Withheld: "#d9644a",
  "Extra stock target": "#e8b84a", "Bought while warned": "#5a8fd9", "Paid while warned": "#b07ad9" };

/** Delayed information, its measured winter outcome, and actual purchases under warning. */
export function HarvestForecasts({ bundle, snapshot, currentTurn, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const record = observationAt(snapshot, "harvest_forecasts");
  const at = snapshot?.turn ?? currentTurn;
  const series = useMemo(() => harvestForecastSeries(bundle.history, at), [bundle.history, at]);
  if (!hasObservation(bundle.history, "harvest_forecasts")) return null;
  if (!record) return <section className="systems-section" aria-label="Harvest forecasts">
    <h3>Harvest forecasts</h3><p className="systems-note">No usable harvest-forecast observation at turn {currentTurn}. Missing, stale or future-dated evidence is unknown here, including aggregate scores and preparedness.</p>
  </section>;
  const totals = forecastTotals(record);
  const reports = record.reports.filter((row) => row.issued_turn <= record.source_turn);
  const outcomes = record.outcomes.filter((row) => row.resolved_turn != null && row.resolved_turn <= record.source_turn);
  return <section className="systems-section" aria-label="Harvest forecasts">
    <h3>Harvest forecasts · snapshot {at}</h3>
    <p className="systems-note">Report state after simulation turn {record.source_turn}. A pending or withheld report has not informed its recipient. Probability is the predicted risk of winter production falling short of food demand; confidence describes measurement completeness. Neither is an observation of famine.</p>
    <div className="systems-tiles">
      <StatTile label="Reports delivered" value={totals.delivered} detail="currently active" />
      <StatTile label="Reports pending" value={totals.pending} />
      <StatTile label="Reports withheld" value={totals.withheld} />
      <StatTile label="Received while warned" value={show(totals.bought)} detail="grain bought this completed turn" />
      <StatTile label="Paid while warned" value={show(totals.paid)} detail="actual treasury payments this turn" />
      <StatTile label="Mean Brier score" value={totals.brier == null ? "Not yet scored" : show(totals.brier)} detail={`${record.counters.resolved ?? 0} scored reports; lower is better`} />
    </div>
    <div className="systems-chart-pair">
      <CivLineChart data={series} civs={["Pending", "Delivered", "Withheld"]} color={(name) => COLORS[name]}
        currentTurn={at} label="Harvest report delivery over time" step />
      <CivLineChart data={series} civs={["Extra stock target", "Bought while warned"]} color={(name) => COLORS[name]}
        currentTurn={at} label="Recorded preparedness target and purchases" format={show} step />
    </div>
    <h4>Active assessments</h4>
    {reports.length === 0 ? <p className="systems-note">No active report recorded in this snapshot.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Harvest reports at snapshot ${at}`}>
        <thead><tr><th>Report</th><th>Recipient</th><th>Ruler at issue</th><th>Observer</th><th>Status</th><th>Issued</th><th>Planned / actual delivery</th><th>Expires</th><th>Winter window</th><th>Shortfall risk</th><th>Confidence</th><th>Predicted production ÷ demand</th></tr></thead>
        <tbody>{reports.map((row) => <tr key={row.id}>
          <td>{row.id}</td><td><button type="button" className="systems-link" onClick={() => onSelectRegion(row.recipient_region_name)}>{row.recipient_region_name}</button></td>
          <td><button type="button" className="systems-link" onClick={() => onSelectCivilization(row.owner_name)}>{row.owner_name}</button></td>
          <td>{row.source_region_name}</td><td>{row.status}</td><td>{row.issued_turn}</td>
          <td>{row.delivery_turn} / {row.delivered_turn ?? "Not delivered"}</td><td>{row.expires_turn}</td><td>{row.target_start}–{row.target_end}</td>
          <td>{percent(row.probability)}</td><td>{percent(row.confidence)}</td><td>{show(row.predicted_ratio)}</td>
        </tr>)}</tbody>
      </table></div>}
    <h4>Preparedness in simulation turn {record.source_turn}</h4>
    {record.preparedness.length === 0 ? <p className="systems-note">No warning-driven target increment recorded in this turn.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Harvest preparedness at snapshot ${at}`}>
        <thead><tr><th>Region</th><th>Ruler</th><th>Report</th><th>Base stock target</th><th>Extra target</th><th>Grain received</th><th>Treasury paid</th></tr></thead>
        <tbody>{record.preparedness.map((row) => <tr key={row.region}>
          <td><button type="button" className="systems-link" onClick={() => onSelectRegion(row.region_name)}>{row.region_name}</button></td>
          <td>{row.owner_name}</td><td>{row.forecast_id}</td><td>{show(row.base_target)}</td><td>{show(row.extra_target)}</td>
          <td>{show(row.bought_during_warning)}</td><td>{show(row.paid_during_warning)}</td>
        </tr>)}</tbody>
      </table></div>}
    <p className="systems-note">Purchases and payments are actual completed-turn flows during an active warning. They are not estimated extra purchases or losses avoided by the report. Treasury units and grain units stay separate.</p>
    <h4>Resolved assessments retained by this snapshot</h4>
    {outcomes.length === 0 ? <p className="systems-note">No resolved assessment retained yet.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Harvest outcomes at snapshot ${at}`}>
        <thead><tr><th>Report</th><th>Region</th><th>Status</th><th>Resolved</th><th>Original risk</th><th>Observed production ÷ demand</th><th>Shortfall</th><th>Brier score</th></tr></thead>
        <tbody>{outcomes.map((row) => <tr key={row.id}><td>{row.id}</td><td>{row.recipient_region_name}</td><td>{row.status}</td>
          <td>{row.resolved_turn}</td><td>{percent(row.probability)}</td><td>{row.observed_ratio == null ? "Unscored" : show(row.observed_ratio)}</td>
          <td>{row.outcome_shortfall == null ? "Unknown" : row.outcome_shortfall ? "Yes" : "No"}</td><td>{row.brier == null ? "Unscored" : show(row.brier)}</td>
        </tr>)}</tbody>
      </table></div>}
    <p className="systems-note">Outcomes measure winter production against demand before trade and reserve releases. This bounded table can omit older resolved reports. Charts stop at this snapshot; missing history stays unknown.</p>
    {record.calibration.some(([count]) => count > 0) && <>
      <h4>Calibration of scored reports</h4>
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Forecast calibration at snapshot ${at}`}>
        <thead><tr><th>Probability bin</th><th>Scored reports</th><th>Mean predicted risk</th><th>Observed shortfall share</th></tr></thead>
        <tbody>{record.calibration.map(([count, probability, shortfalls], index) => <tr key={index}>
          <td>{index * 20}–{(index + 1) * 20}%</td><td>{count}</td><td>{count ? percent(probability / count) : "Unknown"}</td>
          <td>{count ? percent(shortfalls / count) : "Unknown"}</td>
        </tr>)}</tbody>
      </table></div>
    </>}
  </section>;
}
