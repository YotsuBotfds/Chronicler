import type { Bundle, TurnSnapshot } from "../../types";
import { payrollFunnel, units, workshopFinanceAt } from "../../lib/workshopFinance";
import { show } from "./formatters";

const money = (milli: number) => show(units(milli));
const MODE_NOTE: Record<string, string> = {
  paid: "Paid mode: an academy of the region's ruler buys the firm's wares with treasury money; sales fund wages that replace the crew's ordinary income share for their workshop time.",
  unpaid_labor: "Unpaid-labour ablation: the firm sells and the crew's ordinary income share is still replaced, but no wage is paid.",
  no_customer: "No-customer control: wages are owed but nothing is sold, so unpaid wages cut hours, then crew, then close the firm.",
};

/** Completed-turn workshop payroll records only; never reads final-world state. */
export function WorkshopFinance({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const record = workshopFinanceAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Workshop payroll">
    <h3>Workshop payroll</h3><p className="systems-note">Workshop payroll is not observed or is unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const receipts = new Map((record.receipts ?? []).map((r) => [r.site, r]));
  const civ = (index: number | null | undefined) =>
    index === null || index === undefined || index < 0 ? "None" : civs[index]?.name ?? `Civ ${index}`;
  const f = payrollFunnel(record);
  return <section className="systems-section" aria-label="Workshop payroll">
    <h3>Workshop payroll · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Amounts are treasury units (one unit is also one unit of a person's wealth); wares are loads. A firm opens around an academy order, holds title only to its own output that the region's market did not use first, and never borrows.</p>
    {record.firms.length === 0 ? <p className="systems-note">No firm is open.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Workshop firms at snapshot ${turn}`}>
        <thead><tr><th>City</th><th>Region</th><th>Ruler</th><th>Cash</th><th>Wares held</th><th>Crew paid</th><th>Sold</th><th>Sales</th><th>Wages paid / due</th><th>Ordinary income replaced</th><th>Owed</th><th>Hours · crew cap next</th></tr></thead>
        <tbody>{record.firms.map((firm) => {
          const r = receipts.get(firm.site);
          return <tr key={firm.site}>
            <td>{firm.city_name}</td>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(regions[firm.region].name)}>{regions[firm.region].name}</button></td>
            <td>{civ(r?.controller)}</td>
            <td>{money(firm.cash)}</td>
            <td>{money(firm.inventory)}</td>
            <td>{r ? r.crew.length : "Unknown"}</td>
            <td>{r ? money(r.sold) : "Unknown"}</td>
            <td>{r ? money(r.sales) : "Unknown"}</td>
            <td>{r ? `${money(r.wages_paid)} / ${money(r.wages_due)}` : "Unknown"}</td>
            <td>{show(r?.income_replaced)}</td>
            <td>{money(firm.owed.reduce((sum, o) => sum + o.amount, 0))}{firm.insolvent_run ? ` (insolvent ${firm.insolvent_run} turns)` : ""}</td>
            <td>{`${show(firm.hours)} · ${firm.crew_cap}`}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    {record.receipts === null ? <p className="systems-note">No payroll pass was recorded in simulation turn {record.source_turn}; sales and wages are unknown, not zero.</p> : null}
    <table className="systems-table" aria-label={`Payroll funnel to snapshot ${turn}`}>
      <tbody>
        <tr><th scope="row">Operating site-turns with paid crews</th><td>{show(f.operatingSiteTurns)}</td></tr>
        <tr><th scope="row">Firm-turns with wares offered</th><td>{show(f.offeredFirmTurns)}</td></tr>
        <tr><th scope="row">Firm-turns with a paying customer</th><td>{show(f.customerFirmTurns)}</td></tr>
        <tr><th scope="row">Sales paid</th><td>{`${show(f.salesPaid)} (${show(f.sales)} units)`}</td></tr>
        <tr><th scope="row">Wages paid / due</th><td>{`${show(f.wagesPaid)} / ${show(f.wagesDue)}`}</td></tr>
        <tr><th scope="row">Wages written off / lapsed</th><td>{`${show(f.owedWrittenOff)} / ${show(f.owedLapsed)}`}</td></tr>
        <tr><th scope="row">Ordinary income replaced</th><td>{show(f.incomeReplaced)}</td></tr>
        <tr><th scope="row">Crew net (wages − replaced income)</th><td>{show(f.netCrewEffect)}</td></tr>
        <tr><th scope="row">Firms closed for insolvency</th><td>{show(f.closedInsolvent)}</td></tr>
      </tbody>
    </table>
    {record.closed.length > 0 ? <p className="systems-note">Closed firms: {record.closed.map((s) => `${s.city_name} (turn ${s.closed_turn}, ${s.closed_reason?.replace("_", " ")})`).join("; ")}.</p> : null}
  </section>;
}
