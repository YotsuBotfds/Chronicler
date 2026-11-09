import type { Bundle, TurnSnapshot } from "../../types";
import { localBudgetsAt } from "../../lib/localBudgets";
import { obligationTotals, readMaintenanceObligation } from "../../lib/maintenanceObligation";
import { show } from "./formatters";

const MODE_NOTE: Record<string, string> = {
  reserve: "Reserve: before the budget is bargained, each ruler sets aside its planned repair charges, up to a declared share of the budget it would otherwise bargain. Repairs ask the bargained budget only for the rest and may spend the reservation beyond their envelope; each turn's charge is split between the reservation and the envelope pro rata to their amounts.",
  reserve_only: "Reserve-only control: the same reservation, and so the same smaller budget for every bargained service, but repairs stay held to their bargained envelope and the whole reservation is returned unspent. It shows the crowding-out without the repair benefit.",
};

/** Completed-turn maintenance obligation only; never reads final-world state. */
export function MaintenanceObligation({ bundle, snapshot, currentTurn }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readMaintenanceObligation(snapshot, civs.length);
  const at = snapshot?.turn ?? currentTurn;
  if (reading.status !== "ok") return <section className="systems-section" aria-label="Maintenance obligation">
    <h3>Maintenance obligation</h3>
    <p className="systems-note">{reading.status === "absent"
      ? `The maintenance obligation is not observed at snapshot ${at}.`
      : `The maintenance obligation record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const c = (key: string) => record.counters[key] ?? 0;
  const civ = (index: number) => civs[index]?.name ?? `Civ ${index}`;
  const totals = obligationTotals(record);
  // The budget left to bargain comes from local budgets' own dated decision of the same turn and ruler.
  const budgets = localBudgetsAt(snapshot, civs.length);
  const after = new Map((budgets?.decisions ?? []).filter((d) => d.turn === record.source_turn).map((d) => [d.civ, d.budget]));
  const known = budgets !== null && budgets.decisions !== null;
  const removed = (civIndex: number, before: number) => {
    const budget = after.get(civIndex);
    return budget === undefined ? null : before - budget;
  };
  const crowded = record.decisions === null || !known ? null
    : record.decisions.every((d) => after.has(d.civ)) ? record.decisions.reduce((a, d) => a + (removed(d.civ, d.budget_before) ?? 0), 0) : null;
  return <section className="systems-section" aria-label="Maintenance obligation">
    <h3>Maintenance obligation · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">The reservation is RS2&apos;s planned per-turn charges for the ruler&apos;s open repairs, capped at {show(record.parameters.max_budget_share * 100)}% of the budget it would have without it. It is an obligation, not a bargained promise: it has no sponsor and moves no grievance, and what repairs do not use is returned to the treasury. Every reservation lowers the budget bargained for every other service (the crowding-out). Money in whole treasury units.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Maintenance obligation to snapshot ${turn}`}>
      <thead><tr><th>Lifetime</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Planned repair charges at decision</td><td>{show(c("planned_coins"))}</td></tr>
        <tr><td>Reserved (decisions where the cap bound)</td><td>{show(c("reserved_coins"))} ({show(c("cap_binding"))})</td></tr>
        <tr><td>Used by repairs · returned unspent</td><td>{show(c("used_coins"))} · {show(c("returned_coins"))}</td></tr>
        <tr><td>Repairs charged: from the reservation · from the bargained envelope</td><td>{show(c("used_coins"))} · {show(c("envelope_spent_coins"))} (of {show(c("charged_coins"))})</td></tr>
      </tbody>
    </table></div>
    {record.decisions === null
      ? <p className="systems-note">No budget decision was recorded in simulation turn {record.source_turn}; reservations for the next turn are unknown, not zero.</p>
      : record.decisions.length === 0 ? <p className="systems-note">No ruler decided a budget this turn.</p> : <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Reservations decided at snapshot ${turn}`}>
          <thead><tr><th>Ruler</th><th>Planned repair charges</th><th>Budget before</th><th>Cap</th><th>Reserved for next turn</th><th>Budget left to bargain</th><th>Crowded out</th></tr></thead>
          <tbody>{record.decisions.map((d) => {
            const gone = known ? removed(d.civ, d.budget_before) : null;
            return <tr key={d.civ}>
              <td>{civ(d.civ)}</td><td>{d.planned}</td><td>{d.budget_before}</td><td>{d.cap}{d.planned > d.cap ? " (binding)" : ""}</td>
              <td>{d.reserved}</td><td>{show(known ? after.get(d.civ) : null)}</td><td>{show(gone)}</td>
            </tr>;
          })}</tbody>
        </table></div>
        <p className="systems-note">Decided this turn: {show(totals.reserved)} reserved of {show(totals.planned)} planned ({show(totals.capped)} rulers capped). {crowded === null
          ? "The budget left to bargain is unknown: the local budgets decision of this turn is not readable."
          : `Bargained budgets are ${show(crowded)} lower in all than without the reservations.`}</p>
      </>}
    {record.uses === null
      ? <p className="systems-note">No repair charge was settled in simulation turn {record.source_turn}; how reservations were used is unknown, not zero.</p>
      : record.uses.length === 0 ? <p className="systems-note">No ruler held a reservation or a repair charge this turn.</p> : <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Reservations used at snapshot ${turn}`}>
          <thead><tr><th>Ruler</th><th>Reserved</th><th>Repairs charged</th><th>Paid from the reservation</th><th>Paid from the envelope (of it)</th><th>Envelope&apos;s share of the work</th><th>Returned unspent</th></tr></thead>
          <tbody>{record.uses.map((u) => <tr key={u.civ}>
            <td>{civ(u.civ)}</td><td>{u.reserved}</td><td>{u.charged}</td><td>{u.used}</td>
            <td>{u.envelope_spent} ({u.envelope === null ? "no envelope" : u.envelope})</td>
            <td>{u.envelope_share === undefined ? "Not recorded (reservation paid first)" : show(u.envelope_share)}</td><td>{u.returned}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="systems-note">Used this turn: {show(totals.used)} from reservations and {show(totals.envelopeSpent)} from envelopes of {show(totals.charged)} charged; {show(totals.returned)} returned{record.mode === "reserve_only" ? " (the control returns everything it reserved)" : ""}.</p>
      </>}
  </section>;
}
