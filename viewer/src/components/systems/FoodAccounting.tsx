import { useState } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import { foodAccountingAt } from "../../lib/foodAccounting";

const show = (value: number | null) => value === null ? "Not observed" : value.toLocaleString(undefined, { maximumFractionDigits: 4 });

export function FoodAccounting({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const regions = bundle.world_state.regions;
  const civs = bundle.world_state.civilizations;
  const record = foodAccountingAt(snapshot, regions.length, civs.length);
  if (!record) return <section className="systems-section" aria-label="Food accounting">
    <h3>Food accounting</h3><p className="systems-note">Food accounting is not observed or is unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const selectedId = selected !== null && selected < regions.length ? selected : (record.regions[0]?.region_id ?? 0);
  const row = record.regions.find((item) => item.region_id === selectedId);
  const native = row?.native;
  const pub = row?.public;
  const nativeRows: Array<[string, number]> = native ? [
    ["Opening stock", native.opening], ["Produced", native.produced], ["Transport net", native.transport_net],
    ["Craft input", native.craft_input], ["Clamp correction", native.clamp_correction], ["Before consumption", native.pre_consumption],
    ["Consumed", native.consumed], ["Storage loss", native.storage_loss], ["Capacity overflow", native.cap_overflow],
    ["Closing stock", native.closing], ["Demand", native.demand], ["Sufficiency before relief", native.sufficiency],
    ["Balance residual", native.balance_residual], ["Balance tolerance", native.balance_tolerance],
  ] : [];
  return <section className="systems-section" aria-label="Food accounting">
    <h3>Food accounting · snapshot {record.completed_turn}</h3>
    <p className="systems-note">Phase 2 of simulation turn {record.source_turn}; mode {record.mode}. Amounts are model food goods, not calories or household meals. Population and native counts are from Phase 2, before later migration or conquest.</p>
    <p className="systems-note">{record.transport === "physical_delivery" ? "Transport net is physical imports and returns minus departures." : record.transport === "abstract_allocation" ? "Transport net is abstract imports minus exports." : "No transport is recorded for this mode."} Native consumption is a regional proportional stock drawdown before public relief; wealth does not restrict native food access.</p>
    {record.regions.length === 0 ? <p className="systems-note">No regional accounting was recorded.</p> : <>
      <label className="phase75-field"><span>Region accounting</span><select aria-label="Region accounting" value={selectedId} onChange={(event) => setSelected(Number(event.target.value))}>
        {regions.map((region, id) => <option key={id} value={id}>{region.name}</option>)}
      </select></label>
      {!row && <p className="systems-note">Accounting for this region is not observed at this snapshot.</p>}
      {row && <>
        <p><button type="button" className="systems-link" onClick={() => onSelectRegion(regions[row.region_id].name)}>{regions[row.region_id].name}</button> · model population {show(row.model_population)} · native count {show(row.native_count)}</p>
        {native ? <>
          {native.pre_consumption <= 0 && native.demand > 0 && <p className="systems-note">Recorded native food before consumption was empty while demand was positive.</p>}
          {native.consumed < native.demand && <p className="systems-note">Native consumption was below recorded demand{pub && pub.released > 0 && row.sufficiency_after_relief !== null && row.sufficiency_after_relief < 1 ? "; public release did not cover the remaining modeled need" : ""}.</p>}
          <div className="systems-table-wrap"><table className="systems-table" aria-label="Native food accounting"><tbody>{nativeRows.map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{show(value)}</td></tr>)}</tbody></table></div>
          <p className="systems-note">Opening + production + transport net − craft input + clamp correction − consumption − storage loss − capacity overflow = closing; compare the recorded residual with tolerance.</p>
        </> : <p className="systems-note">Native food accounting is not observed for this region.{(record.mode === "off" || record.mode === "aggregate") && " Aggregate mode has no native kernel."}</p>}
        <p>Sufficiency after relief: {show(row.sufficiency_after_relief)}</p>
        {pub ? <><h4>Public granary opening</h4><div className="systems-table-wrap"><table className="systems-table" aria-label="Public food accounting"><tbody>
          {([["Keeper", pub.owner_id === -1 ? "Unowned" : civs[pub.owner_id].name], ["Opening", show(pub.opening)], ["Released", show(pub.released)], ["Spoiled", show(pub.spoiled)], ["Abandoned", show(pub.abandoned)], ["Captured custody", show(pub.captured)], ["After opening", show(pub.after_open)], ["Balance residual", show(pub.balance_residual)]] as Array<[string, string]>).map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}
        </tbody></table></div><p className="systems-note">Opening − release − spoilage − abandonment = after opening. Capture changes custody and adds no goods. Public release is modeled as directly eaten, separately from native consumption; this does not establish household distribution. See Public granaries for later arrivals.</p></> : <p className="systems-note">Public granary accounting is not observed for this region.</p>}
      </>}
    </>}
    <h4>Procurement budgets</h4><p className="systems-note">These late Phase 10 budget receipts are separate from this turn&apos;s consumption. A zero budget alone does not establish why procurement did or did not occur; targets may be unknown.</p>
    {record.procurement.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label="Procurement budgets"><thead><tr><th>Civilization</th><th>Initial budget</th><th>Spent</th><th>Remaining</th></tr></thead><tbody>{record.procurement.map((item) => <tr key={item.civilization_id}><td>{civs[item.civilization_id].name}</td><td>{show(item.budget_initial)}</td><td>{show(item.spent)}</td><td>{show(item.budget_remaining)}</td></tr>)}</tbody></table></div> : <p className="systems-note">No procurement budget receipts recorded.</p>}
  </section>;
}
