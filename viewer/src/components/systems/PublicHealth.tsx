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
      <p className="systems-note">Regional epidemic observations remain separate from individual injury care. Local public grain is an internal allocation; foreign supplies pay their controller. Decisions use delayed reports and prior observed fatality. Imported-food cost by origin is unavailable; the policy uses a recorded goods-contact proxy.</p>
      <h4>Patient supplies</h4>
      {record.supply_turn === null ? <p>Supply settlement not observed.</p> : record.supplies.length === 0 ? <p>No patient supplies requested.</p> : <div className="systems-table-wrap"><table>
        <thead><tr><th>Care region</th><th>Source</th><th>Food consumed</th><th>Cash paid</th><th>Internal value</th><th>Outcome</th></tr></thead>
        <tbody>{record.supplies.map((r, i) => <tr key={i}><td>{names[r.region]}</td><td>{r.source === null ? "unobserved" : names[r.source]}</td>
          <td>{(r.food_milli / 1000).toFixed(3)}</td><td>{(r.charged_milli / 1000).toFixed(3)}</td><td>{(r.internal_milli / 1000).toFixed(3)}</td><td>{r.reason}</td></tr>)}</tbody>
      </table></div>}
      <h4>Water service and displacement</h4>
      {record.environment_turn === null ? <p>Epidemic environment not observed.</p> : <ul>{record.environment.filter(r => r.displaced_share > 0 || r.water_service > 0).map(r => <li key={r.region}>{names[r.region]}: {r.residence_observed ? `${(100 * r.displaced_share).toFixed(1)}% displaced` : "residence unobserved"}; {r.sanitation_observed ? `water service ${(100 * r.water_service).toFixed(0)}%, flux susceptibility ×${r.flux_factor.toFixed(2)}` : "water service unobserved"} (source turn {r.source_turn}).</li>)}</ul>}
      <h4>Delivered advice</h4>
      {record.report_turn === null ? <p>Reports not observed.</p> : record.decisions.length === 0 ? <p>No delivered foreign outbreak advice.</p> : <ul>{record.decisions.map(r => <li key={`${r.civ}:${r.target}`}>{civs[r.civ]} → {civs[r.target]}: {r.close ? "close" : "remain open"}; expected loss {r.expected_loss_units.toFixed(3)} against cost {r.cost_units.toFixed(3)}; {r.fatality_observed ? "prior own fatality observed" : "own fatality unobserved"}; reports {r.report_ids.join(", ")}.</li>)}</ul>}
      <h4>Named border guards</h4>
      {record.guard_turn === null ? <p>Guard staffing not observed.</p> : record.guards.length === 0 ? <p>No border watch proposed.</p> : <ul>{record.guards.map(r => <li key={`${r.civ}:${r.target}`}>{civs[r.civ]} → {civs[r.target]}: {r.members.length} guards, {r.work.toFixed(3)} worker-turns, {r.payment}; {r.staffed ? "staffed for the next turn" : "no closure capacity"}. Stable IDs: {r.members.map(m => m.agent_id).join(", ")}.</li>)}</ul>}
    </>}
  </section>;
}
