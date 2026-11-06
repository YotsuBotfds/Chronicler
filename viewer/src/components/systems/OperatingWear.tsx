import type { Bundle, TurnSnapshot } from "../../types";
import { readOperatingWear, wearTotals } from "../../lib/operatingWear";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
/** L1's operating gate: below it a worn site stops until repaired. */
const OPERATE_CONDITION = 0.5;

/** Completed-turn workshop operating wear only; never reads final-world state. */
export function OperatingWear({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const reading = readOperatingWear(snapshot, regions.length);
  const at = snapshot?.turn ?? currentTurn;
  if (reading.status !== "ok") return <section className="systems-section" aria-label="Operating wear">
    <h3>Operating wear</h3>
    <p className="systems-note">{reading.status === "absent"
      ? `Operating wear is not observed at snapshot ${at}.`
      : `The operating wear record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const c = (key: string) => record.counters[key] ?? 0;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const totals = wearTotals(record);
  return <section className="systems-section" aria-label="Operating wear">
    <h3>Operating wear · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. A funded operating workshop loses {show(record.parameters.operating_wear)} of condition a turn, less the upkeep its qualified crew members give; below {OPERATE_CONDITION} it stops until it is repaired. This is a declared maintenance assumption, not calibrated: it moves no money and takes no crew time. The switch has no mode; its comparison is the run without it (workshops alone).</p>
    <p className="systems-note">{record.with_apprenticeship
      ? "Apprenticeship is on: it applies the same wear itself, and this record only reports it with apprenticeship's upkeep offsets."
      : "Apprenticeship is off: nobody is qualified, so nothing offsets the wear and every operating site loses all of it."}</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Operating wear to snapshot ${turn}`}>
      <thead><tr><th>Lifetime</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Operating site-turns worn</td><td>{show(c("operating_site_turns"))}</td></tr>
        <tr><td>Wear − upkeep offset = net wear</td><td>{show(c("wear"))} − {show(c("upkeep_offset"))} = {show(c("net_wear"))}</td></tr>
        <tr><td>Site-turns covered by a qualified crew member</td><td>{show(c("covered_site_turns"))}</td></tr>
        <tr><td>Site-turns with the wear fully offset</td><td>{show(c("full_offset_site_turns"))}</td></tr>
        <tr><td>Workshop lump repairs paid</td><td>{show(c("repairs"))}</td></tr>
      </tbody>
    </table></div>
    {record.receipts === null || totals === null
      ? <p className="systems-note">No workshop settlement was recorded in simulation turn {record.source_turn}; this turn&apos;s wear is unknown, not zero.</p>
      : record.receipts.length === 0 ? <p className="systems-note">No funded workshop operated this turn, so none was worn.</p> : <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Worn sites at snapshot ${turn}`}>
          <thead><tr><th>Site</th><th>Region</th><th>Wear − offset = net</th><th>Condition</th><th>Qualified on the crew</th></tr></thead>
          <tbody>{record.receipts.map((r) => <tr key={r.site}>
            <td>Site {r.site}</td>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(region(r.region))}>{region(r.region)}</button></td>
            <td>{show(r.wear)} − {show(r.upkeep_offset)} = {show(r.net_wear)}{r.full_offset ? " (fully offset)" : ""}</td>
            <td>{show(r.condition_before)} → {show(r.condition_after)}{r.condition_before >= OPERATE_CONDITION && r.condition_after < OPERATE_CONDITION ? " (now below the operating gate)" : ""}</td>
            <td>{r.qualified_on_crew.length ? r.qualified_on_crew.join(", ") : "nobody"}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="systems-note">This turn: {totals.sites} sites lost {show(totals.net)} of condition in all ({show(totals.wear)} worn, {show(totals.offset)} offset by upkeep); {totals.covered} had a qualified crew member, {totals.fullOffset} were fully offset{totals.stopping ? `, and ${totals.stopping} fell below the operating gate` : ""}.</p>
      </>}
  </section>;
}
