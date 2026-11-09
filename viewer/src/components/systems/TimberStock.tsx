import type { Bundle, TurnSnapshot } from "../../types";
import { readTimberStock } from "../../lib/recordReading";
import type { TimberStockRow } from "../../lib/timberStock";
import { show } from "./formatters";
import { SystemSection } from "./SystemSection";
import { SystemTable } from "./SystemTable";

const binding = (row: TimberStockRow) => row.capped === null ? "Not observable" : row.capped ? "Yes" : "No";

/** Completed-turn timber accounts only; never reads final-world stock state. */
export function TimberStock({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const reading = readTimberStock(bundle, snapshot, currentTurn);
  if (reading.record === null) return <SystemSection label="Timber stock" emptyText={reading.note} />;
  const record = reading.record;
  const totals = record.totals;
  return <SystemSection label="Timber stock" title={<>Timber stock · snapshot {record.completed_turn}</>}
    note={<>Phase 2 of simulation turn {record.source_turn}. Amounts are timber goods, the units of the economy&apos;s slot output. {record.enforce_cap
      ? "The standing stock capped each timber slot's harvest."
      : "Ablation: the stock is accounted but no harvest cap was applied; overdraft is harvest beyond the stock."}</>}>
    {reading.state === "recorded_zero" ? <p className="systems-note">{reading.note}</p> : null}
    <p className="systems-note">Cleared timber stood on forest cover lost before the harvest (clearing, cooling, wildfire or succession); it is not extraction. Regrowth is logistic toward the cover-scaled capacity and stops while water is below the forest regrowth gate.</p>
    {!record.observed || !totals || !record.regions ? <p className="systems-note">No timber account was settled in simulation turn {record.source_turn}; flows are unknown, not zero.</p> : <>
      <SystemTable label={`Timber totals at snapshot ${record.completed_turn}`}><tbody>
        {([["Opening stock", show(totals.opening)], ["Cleared with cover", show(totals.cleared)], ["Extraction", show(totals.extraction)],
          ...(record.enforce_cap ? [] : [["Overdraft", show(totals.overdraft)]]), ["Regrowth", show(totals.regrowth)],
          ["Removed (no longer timber)", show(totals.removed)], ["Closing stock", show(totals.stock)], ["Capacity", show(totals.capacity)],
          ["Slots where the cap bound", `${totals.capped_slots} of ${totals.slots}`]] as Array<[string, string]>).map(([label, value]) =>
          <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}
      </tbody></SystemTable>
      {record.regions.length === 0 ? <p className="systems-note">No region has a timber slot.</p> :
        <SystemTable label={`Timber accounts at snapshot ${record.completed_turn}`}>
          <thead><tr><th>Region</th><th>Slot</th><th>Stock</th><th>Capacity</th><th>Extraction</th><th>Regrowth</th><th>Cleared</th>{record.enforce_cap ? <th>Cap bound</th> : <th>Overdraft</th>}</tr></thead>
          <tbody>{record.regions.map((row) => <tr key={`${row.region_id}:${row.slot}`}>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(regions[row.region_id].name)}>{regions[row.region_id].name}</button></td>
            <td>{row.slot}</td><td>{show(row.stock)}</td><td>{show(row.capacity)}</td><td>{show(row.extraction)}</td>
            <td>{show(row.regrowth)}{row.water_gate_open ? "" : " (dry)"}</td><td>{show(row.cleared)}</td>
            <td>{record.enforce_cap ? binding(row) : show(row.overdraft)}</td>
          </tr>)}</tbody>
        </SystemTable>}
      <p className="systems-note">Opening − cleared − (extraction − overdraft) + regrowth − removed = closing stock, checked every turn. A zero cap binds only where farmers and a positive timber yield could have harvested.</p>
    </>}
  </SystemSection>;
}
