import type { Bundle, TurnSnapshot } from "../../types";
import { relocationAt, relocationFunnel, units } from "../../lib/relocation";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const MODE_NOTE: Record<string, string> = {
  paid: "Paid: a household's adult movers pay the fare after the move is applied.",
  assisted: "Assisted: as paid, and the destination's ruler funds part of the fare for households short of it, from a bounded share of its treasury.",
  liquidity_only: "Liquidity only (control): the fare must be held to move, but nothing is paid.",
};

/** Completed-turn relocation receipts only; never reads final-world state. */
export function Relocation({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const record = relocationAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Relocation costs">
    <h3>Relocation costs</h3><p className="systems-note">Relocation costs are not observed or are unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const name = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const civ = (index: number) => (index < 0 ? "None" : civs[index]?.name ?? `Civ ${index}`);
  const link = (index: number) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(name(index))}>{name(index)}</button>;
  return <section className="systems-section" aria-label="Relocation costs">
    <h3>Relocation costs · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]} The fare is {show(units(record.parameters.fare_milli ?? 0))} per person, children included; it goes to travel costs (provisions, carts, tolls), not to anyone. Arrivals get nothing automatically: they share the destination's food, work and care.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Relocation funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Households</th></tr></thead>
      <tbody>{relocationFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}
        <tr><td>Fares paid by movers</td><td>{show(units(record.counters.fare_debited_milli ?? 0))}</td></tr>
        <tr><td>Assistance paid by rulers</td><td>{show(units(record.counters.assistance_charged_milli ?? 0))}</td></tr>
      </tbody>
    </table></div>
    {record.households === null ? <p className="systems-note">No relocation turn was recorded in simulation turn {record.source_turn}; moves and payments are unknown, not zero.</p> :
      record.households.length === 0 ? <p className="systems-note">No household tried to move.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Households at the fare gate at snapshot ${turn}`}>
        <thead><tr><th>Household</th><th>From → to</th><th>People (children)</th><th>Gate</th><th>Moved</th><th>Fare</th><th>Assistance</th><th>Paid</th><th>Unpaid</th></tr></thead>
        <tbody>{record.households.map((h) => <tr key={`${h.turn}-${h.lead}`}>
          <td>{h.lead}{h.is_return ? " (return)" : ""}</td>
          <td>{link(h.from_region)} → {link(h.to_region)}</td>
          <td>{h.members.length} ({h.children})</td>
          <td>{words(h.reason)}</td>
          <td>{h.applied ? "Yes" : "No"}</td>
          <td>{show(units(h.fare))}</td>
          <td>{h.assistance ? `${show(units(h.assistance))} from ${civ(h.payer)}${h.assistance_status ? ` (${words(h.assistance_status)})` : ""}` : "—"}</td>
          <td>{record.mode === "liquidity_only" ? "Not charged" : show(units(h.paid))}</td>
          <td>{h.residual ? show(units(h.residual)) : "—"}</td>
        </tr>)}</tbody>
      </table></div>}
    {record.households_dropped ? <p className="systems-note">{record.households_dropped} more households are counted in the funnel but not listed.</p> : null}
    {record.regions && record.regions.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Receiving pressure at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Arrivals (households, assisted)</th><th>Departures</th><th>People per capacity before → after</th><th>Food sufficiency</th></tr></thead>
        <tbody>{record.regions.map((r) => <tr key={r.region}>
          <td>{link(r.region)}</td>
          <td>{r.arrivals} ({r.arrival_households}, {r.assisted_households})</td>
          <td>{r.departures}</td>
          <td>{show(r.pressure_before, 2)} → {show(r.pressure_after, 2)}</td>
          <td>{show(r.food_sufficiency, 2)}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.services && record.services.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Arrivals' service at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Arrived in turn</th><th>Food signal</th><th>Arrivals' mean ration</th><th>Residents' mean ration</th></tr></thead>
        <tbody>{record.services.map((s) => <tr key={`${s.region}-${s.arrival_turn}`}>
          <td>{link(s.region)}</td><td>{s.arrival_turn}</td><td>{show(s.food_sufficiency, 2)}</td>
          <td>{show(s.arrivals_mean_ration, 2)}</td><td>{show(s.residents_mean_ration, 2)}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.assistance && record.assistance.length > 0 ? <p className="systems-note">Assistance settled: {record.assistance.map((a) =>
      `${civ(a.civ)} ${words(a.status)} (${show(units(a.granted))} granted, ${a.charged_coins} paid)`).join("; ")}.</p> : null}
  </section>;
}
