import type { Bundle, TurnSnapshot } from "../../types";
import { harvestCoverAt } from "../../lib/harvestCover";

export function HarvestCover({ bundle, snapshot, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions;
  const reading = harvestCoverAt(snapshot, regions.length);
  return <section className="systems-section" aria-label="Harvest and canopy">
    <h3>Harvest and canopy · snapshot {snapshot?.turn}</h3>
    {reading.status !== "recorded" ? <p className="systems-note">{reading.status === "malformed" ? "Malformed canopy record; nothing is inferred." : "Canopy response is unknown at this snapshot, not zero."}</p> : <>
      <p className="systems-note">Simulation turn {reading.record!.source_turn}. {reading.record!.mode === "record_only" ? "Record only: proposed gaps were not applied." : "Depleted stands open canopy gaps. Ecology owns regrowth; standing timber is preserved."}</p>
      <div className="systems-table-wrap"><table className="systems-table" aria-label="Canopy response this turn">
        <thead><tr><th>Region</th><th>Stand / capacity</th><th>Canopy before → after</th><th>Applied gap</th></tr></thead>
        <tbody>{reading.record!.rows!.length === 0 ? <tr><td colSpan={4}>No positive-capacity timber stand was recorded (recorded: none).</td></tr> : reading.record!.rows!.map((r) => <tr key={r.region}>
          <td><button className="systems-link" onClick={() => onSelectRegion(regions[r.region].name)}>{regions[r.region].name}</button></td>
          <td>{r.standing.toFixed(2)} / {r.capacity.toFixed(2)}</td><td>{r.cover_before.toFixed(3)} → {r.cover_after.toFixed(3)}</td><td>{r.loss.toFixed(4)}</td>
        </tr>)}</tbody></table></div>
    </>}
  </section>;
}
