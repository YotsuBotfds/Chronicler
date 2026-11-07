import type { Bundle, TurnSnapshot } from "../../types";
import { readPublicHealth } from "../../lib/publicHealth";

export function PublicHealth({ bundle, snapshot, currentTurn }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number;
}) {
  const reading = readPublicHealth(bundle, snapshot, currentTurn);
  if (reading.state === "disabled") return null;
  const record = reading.record;
  const names = bundle.world_state.regions.map(r => r.name);
  const civs = bundle.world_state.civilizations.map(c => c.name);
  return <section className="systems-section" aria-label="Connected public health">
    <h3>Connected public health</h3>
    {reading.note && <p role={reading.state === "malformed" ? "alert" : undefined}>{reading.note}</p>}
    {record && <>
      <p>{record.mode === "active" ? "Care and maintained water service" : "Cost control: supplies and wages, no protective effect"} · {record.policy} reports.</p>
      <p className="systems-note">Observation from simulation turn {record.source_turn}. Additional report delay: {record.report_delay} turns. Advice uses delivered, unexpired reports.</p>
      <p className="systems-note">{record.crowding === "density_only"
        ? "Corrected explicit density_only mode: regional population density remains the physical health authority. Motive-classified ledger spells add no susceptibility multiplier. Recent arrivals are diagnostics, not measured housing pressure."
        : `Legacy displacement coupling${record.crowding_recorded ? "" : " (implicit in this older record)"}: the recorded motive-classified spell share contributes to susceptibility. An unknown reason can change that classification; it is not a measurement of physical crowding.`}</p>
      <p className="systems-note">Regional epidemic observations remain separate from individual injury care. Local public grain is an internal allocation; foreign supplies pay their controller. Decisions use delayed reports and prior observed fatality. Imported-food cost by origin is unavailable; the policy uses a recorded goods-contact proxy.</p>
      <h4>Funding</h4>
      {record.funding_turn === null ? <p>Cash funding not recorded in this observation.</p> : record.funding.length === 0 ? <p>No care or public-health envelope executed.</p> : <ul>{record.funding.map(f => <li key={f.civ}>{civs[f.civ]}: {((f.care_cash_milli + f.supply_cash_milli + f.guard_cash_milli) / 1000).toFixed(3)} cash charged within {(f.envelope_milli / 1000).toFixed(3)} envelope; care carry {(f.care_carry_before / 1000).toFixed(3)} → {(f.care_carry_after / 1000).toFixed(3)}, guard carry {(f.guard_carry_before / 1000).toFixed(3)} → {(f.guard_carry_after / 1000).toFixed(3)}. Local grain value also uses the gross envelope.</li>)}</ul>}
      <h4>Patient supplies</h4>
      {record.supply_turn === null ? <p>Supply settlement not observed.</p> : record.supplies.length === 0 ? <p>No patient supplies requested.</p> : <div className="systems-table-wrap"><table>
        <thead><tr><th>Care region</th><th>Source</th><th>Food consumed</th><th>Cash paid</th><th>Internal value</th><th>Outcome</th></tr></thead>
        <tbody>{record.supplies.map((r, i) => <tr key={i}><td>{names[r.region]}</td><td>{r.source === null ? "unobserved" : names[r.source]}</td>
          <td>{(r.food_milli / 1000).toFixed(3)}</td><td>{(r.charged_milli / 1000).toFixed(3)}</td><td>{(r.internal_milli / 1000).toFixed(3)}</td><td>{r.reason}</td></tr>)}</tbody>
      </table></div>}
      <h4>Water service and prior residence observations</h4>
      {record.environment_turn === null ? <p>Epidemic environment not observed.</p> : <ul>{record.environment.map(r => <li key={r.region}>{names[r.region]}: {r.residence_observed ? `${(100 * r.displaced_share).toFixed(1)}% in motive-classified spells` : "residence unobserved"}; {r.sanitation_observed ? `water service ${(100 * r.water_service).toFixed(0)}%, flux susceptibility ×${r.flux_factor.toFixed(2)}` : "water service unobserved"}; extra susceptibility ×{r.crowding_factor.toFixed(2)} ({r.crowding_basis}); {r.arrival_diagnostics_complete === true && r.recent_arrival_share !== null ? `recent residence arrivals ${(100 * r.recent_arrival_share).toFixed(1)}% (complete window and coverage)` : `recent residence arrival share unknown${r.arrival_diagnostics_complete === false ? " (incomplete window or coverage)" : " (not recorded)"}`} (residence/water source turn {r.source_turn}; multiplier source turn {r.crowding_source_turn}).</li>)}</ul>}
      <h4>Delivered advice</h4>
      {record.report_turn === null ? <p>Reports not observed.</p> : record.decisions.length === 0 ? <p>No delivered foreign outbreak advice.</p> : <ul>{record.decisions.map(r => <li key={`${r.civ}:${r.target}`}>{civs[r.civ]} → {civs[r.target]}: {r.close ? "close" : "remain open"}; expected loss {r.expected_loss_units.toFixed(3)} against cost {r.cost_units.toFixed(3)}; {r.fatality_observed ? "prior own fatality observed" : "own fatality unobserved"}; reports {r.report_ids.join(", ")}.</li>)}</ul>}
      <h4>Named border guards</h4>
      {record.guard_turn === null ? <p>Guard staffing not observed.</p> : record.guards.length === 0 ? <p>No border watch proposed.</p> : <ul>{record.guards.map(r => <li key={`${r.civ}:${r.target}`}>{civs[r.civ]} → {civs[r.target]}: {r.members.length} guards, {r.work.toFixed(3)} worker-turns, {r.payment}; {r.staffed ? "staffed for the next turn" : "no closure capacity"}. Stable IDs: {r.members.map(m => m.agent_id).join(", ")}.</li>)}</ul>}
    </>}
  </section>;
}
