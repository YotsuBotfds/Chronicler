import type { Bundle, TurnSnapshot } from "../../types";
import { readGranaryStorage } from "../../lib/recordReading";

const show = (value: number | null) => value === null ? "Not observed" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });

/** Uses the enclosing granary selector; never reads final-world asset state. */
export function GranaryStorage({ bundle, snapshot, region }: { bundle: Bundle; snapshot: TurnSnapshot | null; region: number | null }) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readGranaryStorage(bundle, snapshot);
  const frame = reading.record;
  const at = snapshot?.turn;
  if (!frame) return <section className="systems-stack" aria-label="Granary storage assets">
    <h4>Storage assets</h4><p className="systems-note">{reading.note}</p>
  </section>;
  const ids = regions.map((_, id) => id).filter((id) => region === null || region === id);
  const keeper = (id: number) => id === -1 ? "Unowned" : civs[id].name;
  return <section className="systems-stack" aria-label="Granary storage assets">
    <h4>Storage assets · snapshot {at}</h4>
    {reading.state === "recorded_zero" ? <p className="systems-note">{reading.note}</p> : null}
    <p className="systems-note">Work in Phase 2 of simulation turn {frame.receipt_turn} uses aggregate farmer-equivalent capacity after city and care work, not an individual roster. The treasury and timber costs are recorded service inputs. Unused reserved timber returns after the native economy.</p>
    <p className="systems-note">Effective capacity is built capacity × condition. Damage increases spoilage. Capacity is enforced late in Phase 10 after arrivals: excess public grain returns to the regional market and cannot feed native consumption earlier that turn. Public relief is separate from native consumption.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Storage assets at snapshot ${at}`}>
      <thead><tr><th>Region</th><th>Owner</th><th>Policy / work budget</th><th>Built capacity</th><th>Condition</th><th>Effective capacity</th><th>Repair progress</th><th>Expansion progress</th></tr></thead>
      <tbody>{ids.map((id) => { const asset = frame.assets[id]; const policy = frame.policies[id]; return <tr key={id}>
        <td>{regions[id].name}</td><td>{asset ? keeper(asset.owner) : "Not observed"}</td><td>{policy.policy} / {show(policy.work_budget)}</td>
        <td>{asset ? show(asset.capacity) : "Not observed"}</td><td>{asset ? show(asset.condition) : "Not observed"}</td><td>{asset ? show(asset.capacity * asset.condition) : "Not observed"}</td>
        <td>{asset ? show(asset.repair_progress) : "Not observed"}</td><td>{asset ? show(asset.expansion_progress) : "Not observed"}</td>
      </tr>; })}</tbody>
    </table></div>
    <h4>Storage work and capacity settlement · simulation turn {frame.receipt_turn}</h4>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Storage work at snapshot ${at}`}>
      <thead><tr><th>Region</th><th>Owner / policy</th><th>Work requested / delivered</th><th>Timber reserved / used / returned</th><th>Treasury paid</th><th>Condition before → after</th><th>Capacity before → after</th><th>Repair / expansion progress</th><th>Target requested / feasible</th><th>Grain returned to market</th></tr></thead>
      <tbody>{ids.map((id) => { const receipt = frame.receipts.find((row) => row.region === id); return receipt ? <tr key={id}>
        <td>{regions[id].name}</td><td>{keeper(receipt.owner)} / {receipt.policy}</td><td>{show(receipt.requested)} / {show(receipt.delivered)}</td>
        <td>{show(receipt.timber_reserved)} / {show(receipt.timber_used)} / {show(receipt.timber_returned)}</td><td>{show(receipt.treasury_paid)}</td>
        <td>{show(receipt.condition_before)} → {show(receipt.condition_after)}</td><td>{show(receipt.capacity_before)} → {show(receipt.capacity_after)}</td>
        <td>{show(receipt.repair_progress)} / {show(receipt.expansion_progress)}</td><td>{show(receipt.target_requested)} / {show(receipt.target_feasible)}</td><td>{show(receipt.capacity_returned)}</td>
      </tr> : <tr key={id}><td>{regions[id].name}</td><td colSpan={9}>Work receipt not observed.</td></tr>; })}</tbody>
    </table></div>
  </section>;
}
