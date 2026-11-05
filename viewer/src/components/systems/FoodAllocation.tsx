import type { Bundle, TurnSnapshot } from "../../types";
import { foodAllocationAt, meanShortfall } from "../../lib/foodAllocation";

const show = (value: number | null) => value === null ? "No one" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const REGIME_NOTE: Record<string, string> = {
  equal: "Equal: everyone in a short region eats the region's ration (the identity control).",
  floor_means: "Floor and means: an equal subsistence floor, then the scarce remainder by household means (per-capita adult wealth).",
  targeted_relief: "Targeted relief: market food shared equally; the public granary release goes first to the poorest households.",
};

/** Who ate how much in short regions, from the completed turn's receipts only. */
export function FoodAllocation({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const record = foodAllocationAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Food allocation">
    <h3>Food allocation</h3><p className="systems-note">Food allocation is not observed or is unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const t = record.totals;
  return <section className="systems-section" aria-label="Food allocation">
    <h3>Food allocation · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {REGIME_NOTE[record.regime]} Amounts are rations (1 = a person's food demand). The region's withdrawal is unchanged; the share of anyone who died after Phase 2 is unallocated.</p>
    {!t || !record.regions ? <p className="systems-note">No allocation ran in simulation turn {record.source_turn}; rations are unknown, not zero.</p> : <>
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Food allocation totals at snapshot ${turn}`}><tbody>
        {([["Short regions", String(t.scarce_regions)], ["People in short regions", String(t.alive)],
          ["Rations allocated", show(t.allocated)], ["Unallocated", show(t.unallocated)],
          ["Shortfall (person-rations)", show(t.shortfall)],
          ["Mean shortfall, poorer half of households", show(meanShortfall(t.shortfall_poorer_half, t.people_poorer_half))],
          ["Mean shortfall, richer half of households", show(meanShortfall(t.shortfall_richer_half, t.people_richer_half))],
          ["Mean shortfall, children", show(meanShortfall(t.shortfall_children, t.children))],
          ["Relief to targeted households", show(t.relief_to_targeted) + ((t.relief_unknown_regions ?? 0) > 0
            ? ` (known regions only; unknown in ${t.relief_unknown_regions} region${t.relief_unknown_regions === 1 ? "" : "s"})` : "")]] as Array<[string, string]>).map(([label, value]) =>
          <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}
      </tbody></table></div>
      {record.regions.length === 0 ? <p className="systems-note">No region was short of food.</p> :
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Short regions at snapshot ${turn}`}>
          <thead><tr><th>Region</th><th>Sufficiency</th><th>People</th><th>Households</th><th>Lowest ration</th><th>Highest ration</th><th>Below floor</th><th>Poorer-half shortfall</th><th>Richer-half shortfall</th></tr></thead>
          <tbody>{record.regions.map((r) => <tr key={r.region}>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(regions[r.region].name)}>{regions[r.region].name}</button></td>
            <td>{show(r.sufficiency)}</td><td>{r.alive}</td><td>{r.households}</td><td>{show(r.min_ration)}</td><td>{show(r.max_ration)}</td>
            <td>{r.below_floor}</td><td>{show(meanShortfall(r.shortfall_poorer_half, r.people_poorer_half))}</td>
            <td>{show(meanShortfall(r.shortfall_richer_half, r.people_richer_half))}</td>
          </tr>)}</tbody>
        </table></div>}
      {record.sample && record.sample.length > 0 ? <details><summary>Sample of people (stable, by id)</summary>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Ration sample at snapshot ${turn}`}>
          <thead><tr><th>Person</th><th>Region</th><th>Household</th><th>Ration</th><th>Targeted</th></tr></thead>
          <tbody>{record.sample.map(([id, region, household, ration, targeted]) => <tr key={id}>
            <td>{id}</td><td>{regions[region]?.name ?? region}</td><td>{household}</td><td>{show(ration)}</td><td>{targeted ? "Yes" : "No"}</td>
          </tr>)}</tbody>
        </table></div></details> : null}
    </>}
  </section>;
}
