import type { Bundle, TurnSnapshot } from "../../types";
import { bindingLabel, commonsRulesAt, type CommonsReceipt } from "../../lib/commonsRules";

const show = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const pct = (value: number) => `${Math.round(value * 100)}%`;
const optional = (value: number | null) => value === null ? "Unknown" : show(value);
const FUNNEL: Array<[string, string]> = [
  ["eligible_slot_turns", "Harvested slots observed (slot-turns)"], ["adoption_candidates", "Depleted and harvested (adoption opportunities)"],
  ["adoption_unaffordable", "Opportunities the treasury could not pay"], ["adopted", "Rules adopted"],
  ["rule_slot_turns", "Rule slot-turns"], ["rest_turns", "Of which resting (quota 0)"], ["paid", "Wardens paid (treasury)"],
  ["required", "Wardens required"], ["tightened_turns", "Turns the harvest cap was lowered"],
  ["binding_turns", "Turns the harvest reached the rule's limit"], ["would_bind_turns", "Cost-only turns the rule would have bound"],
  ["excess", "Cost-only harvest above the rule's limit"], ["grievance_added", "City grievance added"],
];

/** Completed-turn commons rule accounts only; never reads final-world rule state. */
export function CommonsRules({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = (bundle.world_state as unknown as { civilizations?: Array<{ name?: unknown }> }).civilizations ?? [];
  const civName = (index: number) => typeof civs[index]?.name === "string" ? civs[index].name as string : `Civilization ${index}`;
  const record = commonsRulesAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Commons rules">
    <h3>Commons rules</h3><p className="systems-note">Commons rules are not observed or are unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const regionLink = (row: { region_id: number }) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(regions[row.region_id].name)}>{regions[row.region_id].name}</button>;
  const limitText = (row: CommonsReceipt) => row.applied ? `${show(row.limit)} of ${show(row.stock_cap)}` : `${show(row.stock_cap)} (open access)`;
  return <section className="systems-section" aria-label="Commons rules">
    <h3>Commons rules · snapshot {record.completed_turn}</h3>
    <p className="systems-note">Phase 2 of simulation turn {record.source_turn}. {record.mode === "enforced"
      ? "Enforced: a paid rule lowers the timber harvest cap of the stands it covers."
      : "Cost-only ablation: rules are adopted and wardens paid exactly as enforced, but no harvest cap is lowered."}</p>
    <p className="systems-note">Owners decide from the timber account settled in an earlier turn, not the current stock. Coverage is the share of the wardens paid for (Commons Management supplies part); the uncovered share of a stand stays open access. Timber in timber goods, payments in treasury.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Commons rule funnel to snapshot ${record.completed_turn}`}><tbody>
      {FUNNEL.filter(([key]) => key in record.counters).map(([key, label]) =>
        <tr key={key}><th scope="row">{label}</th><td>{show(record.counters[key])}</td></tr>)}
    </tbody></table></div>
    {!record.observed || !record.receipts || !record.decisions
      ? <p className="systems-note">No Phase 2 was settled in simulation turn {record.source_turn}; this turn's rule accounts are unknown, not empty.</p>
      : <>
        {record.decisions.map((d) => <p className="systems-note" key={`${d.region_id}:${d.slot}:${d.kind}`}>
          Decision in turn {d.turn}: {d.civ < 0 ? "No controller" : civName(d.civ)} {d.kind} the rule on {regions[d.region_id].name} slot {d.slot} ({d.reason.split("_").join(" ")}).
        </p>)}
        {record.receipts.length === 0 ? <p className="systems-note">No stand is under a rule this turn: every timber slot is open access.</p> :
          <div className="systems-table-wrap"><table className="systems-table" aria-label={`Commons rule accounts at snapshot ${record.completed_turn}`}>
            <thead><tr><th>Region</th><th>Owner</th><th>Rule</th><th>Known stock (turn)</th><th>Quota</th><th>Coverage</th><th>Limit</th><th>Harvest</th><th>{record.mode === "enforced" ? "Bound" : "Would bind"}</th><th>City grievance</th></tr></thead>
            <tbody>{record.receipts.map((row) => <tr key={`${row.region_id}:${row.slot}`}>
              <td>{regionLink(row)}</td><td>{civName(row.owner)}</td>
              <td>{row.status === "rest" ? "Rest" : "Quota"}{row.new ? " (new)" : ""}</td>
              <td>{show(row.observation.stock)} of {show(row.observation.capacity)} ({row.observation.turn})</td>
              <td>{show(row.quota)}</td><td>{pct(row.coverage)} · paid {row.paid} of {row.required}</td>
              <td>{limitText(row)}</td><td>{show(row.extraction)}</td><td>{bindingLabel(row)}</td>
              <td>{row.city === null ? "No city" : show(row.grievance_added)}</td>
            </tr>)}</tbody>
          </table></div>}
        {record.receipts.length > 0 && <div className="systems-table-wrap"><table className="systems-table" aria-label={`Protected region outcomes at snapshot ${record.completed_turn}`}>
          <thead><tr><th>Region</th><th>Craft output</th><th>Raw imports</th><th>Farmer income</th><th>Food</th><th>Neighbouring open harvest</th></tr></thead>
          <tbody>{record.receipts.map((row) => <tr key={`${row.region_id}:${row.slot}`}>
            <td>{regions[row.region_id].name}</td><td>{optional(row.craft_output)}</td><td>{optional(row.raw_imports)}</td>
            <td>{optional(row.farmer_income_modifier)}</td><td>{optional(row.food_sufficiency)}</td>
            <td>{row.neighbour_slots === 0 ? "No neighbouring stand" : `${show(row.neighbour_open_extraction)} in ${row.neighbour_slots} slot(s)`}</td>
          </tr>)}</tbody>
        </table></div>}
      </>}
    <p className="systems-note">A rule protects stock only against harvest; forest cover lost to clearing, cooling or fire takes the timber regardless. Withheld harvest is a production cost to the region; these records are not a welfare judgement.</p>
  </section>;
}
