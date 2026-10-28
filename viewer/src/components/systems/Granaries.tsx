import { useMemo, useState } from "react";
import { granaryAmounts, granaryKeeper, granaryOwnerRows, granarySeries } from "../../lib/granaries";
import type { SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, TurnStrip } from "./SystemParts";

const COLORS: Record<string, string> = {
  Stocks: "#e8b84a", Targets: "#7d8a96", Bought: "#5aa88f", Released: "#5a8fd9", Spoiled: "#d9644a",
};
const show = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });

/** Stocks and completed-turn movements: no inference from end-of-run granaries. */
export function Granaries({ bundle, snapshot, currentTurn, onSeek, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const recorded = bundle.history.some((row) => row.grain_reserves != null);
  const record = snapshot?.grain_reserves;
  const at = snapshot?.turn ?? currentTurn;
  const names = useMemo(() => {
    const out = new Map<number, string>();
    for (const row of bundle.history) {
      if (row.turn > at) break;
      for (const granary of row.grain_reserves?.granaries ?? []) out.set(granary.region, granary.region_name);
    }
    return out;
  }, [bundle.history, at]);
  // A selected region from a later scrub point must not survive before its first record.
  const region = selected !== null && names.has(selected) ? selected : null;
  const series = useMemo(() => granarySeries(bundle.history, at, region), [bundle.history, at, region]);
  const owners = useMemo(() => granaryOwnerRows(bundle.history, at, region), [bundle.history, at, region]);
  if (!recorded) {
    return <section className="systems-section" aria-label="Public granaries">
      <h3>Public granaries</h3><p className="systems-note">This bundle has no per-turn granary record. New runs record it with grain reserves enabled and an agent economy.</p>
    </section>;
  }
  if (!record) {
    return <section className="systems-section" aria-label="Public granaries">
      <h3>Public granaries</h3><p className="systems-note">No granary record at turn {currentTurn}. Stocks and ownership are unknown at this point.</p>
    </section>;
  }
  const totals = granaryAmounts(record);
  const rows = record.granaries.filter((row) => region === null || row.region === region);
  const flows = record.flows.filter((flow) => region === null || flow.region === region);
  return <section className="systems-section" aria-label="Public granaries">
    <h3>Public granaries · snapshot {at}</h3>
    <p className="systems-note">Stocks and targets after simulation turn {record.source_turn}; movements belong to that completed turn. Grain is in goods units. The keeper is the granary&apos;s recorded owner, which can differ from territorial control until the next ownership settlement.</p>
    <div className="systems-tiles">
      <StatTile label="Grain stored" value={show(totals.stock)} detail="all recorded granaries" />
      <StatTile label="Stock target" value={show(totals.target)} />
      <StatTile label="Grain procured" value={show(totals.bought)} detail="received this turn" />
      <StatTile label="Grain released" value={show(totals.released)} detail="eaten this turn" />
      <StatTile label="Storage spoilage" value={show(totals.spoiled)} detail="this turn" />
    </div>
    <label className="phase75-field"><span>Granary history</span>
      <select aria-label="Granary history" value={region ?? "all"} onChange={(event) => setSelected(event.target.value === "all" ? null : Number(event.target.value))}>
        <option value="all">All granaries</option>
        {[...names].map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </select>
    </label>
    <div className="systems-chart-pair">
      <CivLineChart data={series} civs={["Stocks", "Targets"]} color={(name) => COLORS[name]} currentTurn={at} label="Granary stocks and targets" format={show} step />
      <CivLineChart data={series} civs={["Bought", "Released", "Spoiled"]} color={(name) => COLORS[name]} currentTurn={at} label="Granary procurement, releases and spoilage" format={show} step />
    </div>
    <h4>Keepers over time</h4>
    <TurnStrip rows={owners} firstTurn={bundle.history[0]?.turn ?? at} endTurn={at + 1} currentTurn={at}
      label="Granary ownership over time" emptyText="No keeper observations by this turn." onSeek={onSeek}
      onSelectRow={(row) => setSelected(Number(row.id))} isRowSelected={(row) => Number(row.id) === region} />
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Granaries at snapshot ${at}`}>
      <thead><tr><th>Region</th><th>Keeper</th><th>Controller</th><th>Stocks</th><th>Target</th><th>Bought</th><th>Released</th><th>Spoiled</th><th>Seized / abandoned</th></tr></thead>
      <tbody>{rows.map((row) => {
        const amounts = granaryAmounts(record, row.region);
        return <tr key={row.region}>
          <td><button type="button" className="systems-link" onClick={() => onSelectRegion(row.region_name)}>{row.region_name}</button></td>
          <td>{row.owner_name ? <button type="button" className="systems-link" onClick={() => onSelectCivilization(row.owner_name!)}>{granaryKeeper(row)}</button> : granaryKeeper(row)}</td>
          <td>{row.controller ?? "Nobody"}</td><td>{show(row.grain)}</td><td>{row.observed ? show(row.target) : "Not observed"}</td>
          <td>{show(amounts.bought)}</td><td>{show(amounts.released)}</td><td>{show(amounts.spoiled)}</td><td>{show(amounts.seized)} / {show(amounts.abandoned)}</td>
        </tr>;
      })}</tbody>
    </table></div>
    <h4>Movements in simulation turn {record.source_turn}</h4>
    {flows.length === 0 ? <p className="systems-note">No granary movements recorded in this turn.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Granary movements in turn ${record.source_turn}`}>
        <thead><tr><th>Kind</th><th>Granary</th><th>Amount</th><th>Market / previous keeper</th><th>Sent</th><th>Treasury paid</th><th>Food before → after</th></tr></thead>
        <tbody>{flows.map((flow, index) => <tr key={index}>
          <td>{flow.kind}</td><td>{names.get(flow.region) ?? `Region ${flow.region}`}</td><td>{show(flow.amount)}</td>
          <td>{flow.kind === "bought" ? `${bundle.world_state.regions[flow.source]?.name ?? `Region ${flow.source}`} (${flow.seller_name ?? "unknown seller"})` : flow.kind === "captured" ? flow.seller_name ?? "No keeper" : "—"}</td>
          <td>{flow.kind === "bought" ? show(flow.sent) : "—"}</td><td>{flow.kind === "bought" ? flow.cost : "—"}</td>
          <td>{flow.kind === "released" ? `${show(flow.before)} → ${show(flow.after)}` : "—"}</td>
        </tr>)}</tbody>
      </table></div>}
    <p className="systems-note">Procurement receives grain after transit loss (this turn: {show(totals.transit)} lost, {totals.paid} treasury paid). Captured grain changes keeper without adding stock; seized and abandoned grain leave the granary. Missing older records remain gaps. Charts stop at the selected snapshot.</p>
  </section>;
}
