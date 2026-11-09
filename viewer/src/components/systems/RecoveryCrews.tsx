import type { Bundle, TurnSnapshot } from "../../types";
import { crewTotals, isShort, readRecoveryCrews, type CrewMemberRecord, type CrewReceiptRecord } from "../../lib/recoveryCrews";
import { show } from "./formatters";

const coins = (milli: number) => (milli / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const ORIGIN: Record<string, string> = {
  site_city: "farmer of the site's city", urban_farmer: "farmer of another city", rural_farmer: "rural farmer",
  veteran: "veteran (not a farmer)",
};
const MODE_NOTE: Record<string, string> = {
  paid: "Paid: the coins a granary repair costs its ruler are paid as wages to the named crew who did the work, instead of leaving the economy.",
  unpaid: "Unpaid control: the same crews, reservations, withheld income and treasury charge, but no wage is paid; the whole granary coin cost leaves the economy as a material sink, as without crews.",
};

function member(m: CrewMemberRecord): string {
  const wage = m.wage_due_milli ? `, wage ${coins(m.wage_milli)}${m.wage_residual_milli ? ` (+${coins(m.wage_residual_milli)} refused)` : ""}` : "";
  return `${m.agent_id} (${ORIGIN[m.origin] ?? m.origin}${m.veteran && m.origin !== "veteran" ? ", veteran" : ""}; worked ${show(m.worked)} of ${show(m.share)}${wage})`;
}

function work(r: CrewReceiptRecord): string {
  if (r.kind === "workshop") return `${show(r.delivered)} repair work (share ${show(r.members[0]?.share)} each)`;
  const short = r.members.length === 0 && r.planned > 0 ? "no free adult farmer" : isShort(r) ? "crew short of the plan" : "";
  return `${show(r.planned)} planned → ${show(r.requested)} asked → ${show(r.delivered)} done${short ? ` (${short})` : ""}`;
}

/** Completed-turn recovery crews only; never reads final-world state. */
export function RecoveryCrews({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readRecoveryCrews(snapshot, regions.length, civs.length);
  const at = snapshot?.turn ?? currentTurn;
  if (reading.status !== "ok") return <section className="systems-section" aria-label="Recovery crews">
    <h3>Recovery crews</h3>
    <p className="systems-note">{reading.status === "absent"
      ? `Recovery crews are not observed at snapshot ${at}.`
      : `The recovery crews record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const c = (key: string) => record.counters[key] ?? 0;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const civ = (index: number) => civs[index]?.name ?? `Civ ${index}`;
  const totals = crewTotals(record);
  const paid = record.mode === "paid";
  return <section className="systems-section" aria-label="Recovery crews">
    <h3>Recovery crews · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Granary repair work is done by named adult farmers of the granary&apos;s region (veterans first), each reserved for at most their own farm time and losing that share of their ordinary income; their work is taken from farming. Workshop repair crews are drawn from the whole region (and its eligible veterans) rather than the site&apos;s city alone; their wages are on the repair project&apos;s own receipt. Money in coins.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Recovery crews to snapshot ${turn}`}>
      <thead><tr><th>Lifetime</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Granary coins charged to rulers</td><td>{coins(c("granary_coin_cost_milli"))}</td></tr>
        <tr><td>Of them paid as wages to crews · sunk (left the economy)</td><td>{coins(c("granary_wages_milli"))} · {coins(c("granary_sunk_milli"))}</td></tr>
        <tr><td>Wages refused by the wealth ceiling (sunk)</td><td>{coins(c("granary_wage_residual_milli"))}</td></tr>
        <tr><td>Granary crews named (person-turns)</td><td>{show(c("granary_crews"))} ({show(c("granary_crew_person_turns"))})</td></tr>
        <tr><td>Granary work planned · named and done</td><td>{show(c("granary_work_planned"))} · {show(c("granary_work_named"))}</td></tr>
        <tr><td>Granary turns short of the plan · with no free adult farmer</td><td>{show(c("granary_crew_short"))} · {show(c("granary_no_crew"))}</td></tr>
        <tr><td>Workshop repair crews (person-turns)</td><td>{show(c("workshop_crews"))} ({show(c("workshop_crew_person_turns"))})</td></tr>
        <tr><td>Workshop members: site city · other city · rural · veteran</td><td>{show(c("workshop_members_site_city"))} · {show(c("workshop_members_urban_farmer"))} · {show(c("workshop_members_rural_farmer"))} · {show(c("workshop_members_veteran"))}</td></tr>
        <tr><td>Farm labour taken from farming (farmer-turns)</td><td>{show(c("farm_time_removed"))}</td></tr>
        <tr><td>Ordinary income withheld from crew members</td><td>{show(c("income_replaced"))}</td></tr>
        <tr><td>Veteran crew-turns</td><td>{show(c("veterans_placed"))}</td></tr>
      </tbody>
    </table></div>
    {record.rows_dropped > 0 ? <p className="systems-note">{record.rows_dropped} crew receipts beyond the frame bound were not recorded over the run.</p> : null}
    {record.receipts === null || record.ledger === null || totals === null
      ? <p className="systems-note">No repair Phase 2 was settled in simulation turn {record.source_turn}; this turn&apos;s crews, wages and sunk coins are unknown, not zero.</p>
      : record.receipts.length === 0 ? <p className="systems-note">No repair crew worked this turn.</p> : <>
        <p className="systems-note">This turn: rulers were charged {coins(totals.coins)} granary coins, which without crews would all leave the economy. {paid
          ? `${coins(totals.wages)} reached the crews as wages and ${coins(totals.sunk)} was still sunk (wages the wealth ceiling refused).`
          : `All ${coins(totals.sunk)} was sunk: the control pays no wage.`} {totals.people} people on {totals.granaryCrews} granary and {totals.workshopCrews} workshop crews gave up {show(totals.withheld)} ordinary income, and {show(totals.farmTime)} farmer-turns left farming.</p>
        {record.ledger.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Granary crew money at snapshot ${turn}`}>
          <thead><tr><th>Ruler</th><th>Coins charged</th><th>Wages to crews</th><th>Sunk</th><th>Refused by the ceiling</th></tr></thead>
          <tbody>{record.ledger.map((l) => <tr key={l.civ}>
            <td>{civ(l.civ)}</td><td>{coins(l.coin_cost_milli)}</td><td>{coins(l.wages_milli)}</td><td>{coins(l.sunk_milli)}</td><td>{coins(l.wage_residual_milli)}</td>
          </tr>)}</tbody>
        </table></div> : null}
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Crews at snapshot ${turn}`}>
          <thead><tr><th>Project</th><th>Region</th><th>Ruler</th><th>Eligible</th><th>Work</th><th>Crew</th><th>Farm time taken</th><th>Income withheld</th></tr></thead>
          <tbody>{record.receipts.map((r) => {
            const withheld = r.members.map((m) => m.income_replaced);
            return <tr key={r.pid}>
              <td>#{r.pid} {r.kind}</td>
              <td><button type="button" className="systems-link" onClick={() => onSelectRegion(region(r.region))}>{region(r.region)}</button></td>
              <td>{civ(r.payer)}</td>
              <td>{r.eligible}{r.eligible_site_city !== null ? ` (site city alone: ${r.eligible_site_city})` : ""}</td>
              <td>{work(r)}</td>
              <td>{r.members.length ? r.members.map(member).join("; ") : "nobody"}</td>
              <td>{show(r.farm_time_removed)}</td>
              <td>{withheld.some((v) => v === null) ? "Unknown" : show(withheld.reduce<number>((a, v) => a + (v as number), 0))}</td>
            </tr>;
          })}</tbody>
        </table></div>
      </>}
  </section>;
}
