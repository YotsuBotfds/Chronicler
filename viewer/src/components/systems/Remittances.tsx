import type { Bundle, TurnSnapshot } from "../../types";
import { readRemittances } from "../../lib/recordReading";
import { diasporaCounts, remittancesFunnel, units } from "../../lib/remittances";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const money = (milli: number | null | undefined) => (milli === null || milli === undefined ? "Unknown" : show(units(milli)));
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const MODE_NOTE: Record<string, string> = {
  send: "Send: each eligible migrant sends a bounded share of their wealth to one partner at home; a courier fee is paid out of it.",
  record_only: "Record only (control): the same ledger, eligibility and amounts are computed, and nothing is sent.",
};
const UNMET_NOTE: Record<string, string> = {
  no_bond: "no Marriage or Kin bond strong enough",
  recipient_away: "partners alive but not living in the origin",
  recipient_on_trip: "partner in the origin but away on a trip",
};

/** Completed-turn diaspora ledger and remittance receipts only; never reads final-world state. */
export function Remittances({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const reading = readRemittances(bundle, snapshot, currentTurn);
  if (reading.record === null) return <section className="systems-section" aria-label="Remittances">
    <h3>Remittances and diaspora</h3><p className="systems-note">{reading.note}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const p = record.parameters;
  const name = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const link = (index: number) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(name(index))}>{name(index)}</button>;
  const t = record.totals;
  return <section className="systems-section" aria-label="Remittances">
    <h3>Remittances and diaspora · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]} A sender is an adult migrant settled for at least {show(p.settled_turns)} turns at their destination; the recipient is one Marriage or Kin partner (sentiment {show(p.min_sentiment)} or more) living in the region the migrant left: the spouse first, then the strongest bond. The remittance is {show((p.share_permille ?? 0) / 10)}% of wealth above a reserve of {money(p.reserve_milli)}, at most {money(p.cap_milli)} a turn; {show((p.fee_permille ?? 0) / 10)}% of it is the courier's fee, which leaves the economy. Nothing is created: the sender loses what the recipient gains plus the fee.</p>
    <p className="systems-note">The diaspora ledger starts with the first move observed while the switch is on; earlier migrations are not in it.</p>
    {reading.state === "recorded_zero" ? <p className="systems-note">{reading.note}</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Remittance funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{remittancesFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}
        <tr><td>Credited to recipients</td><td>{money(record.counters.credited_milli ?? 0)}</td></tr>
        <tr><td>Courier fees</td><td>{money(record.counters.fee_milli ?? 0)}</td></tr>
        <tr><td>Refunded to senders (recipient at the wealth ceiling)</td><td>{money(record.counters.refunded_milli ?? 0)}</td></tr>
        {record.mode === "record_only" ? <tr><td>Computed, not sent</td><td>{money(record.counters.not_sent_milli ?? 0)}</td></tr> : null}
      </tbody>
    </table></div>
    {record.receipts === null ? <p className="systems-note">No remittance turn was recorded in simulation turn {record.source_turn}; senders, amounts and the diaspora are unknown, not zero.</p> :
      record.receipts.length === 0 ? <p className="systems-note">No remittance this turn.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Remittances at snapshot ${turn}`}>
        <thead><tr><th>Sender</th><th>From</th><th>Recipient</th><th>To</th><th>Requested (fee)</th><th>Sent</th><th>Fee</th><th>Credited</th><th>Refunded</th><th>Status</th></tr></thead>
        <tbody>{record.receipts.map((r) => <tr key={`${r.turn}-${r.sender}`}>
          <td>#{r.sender}</td>
          <td>{link(r.destination)}</td>
          <td>#{r.recipient} ({r.bond}, sentiment {r.sentiment})</td>
          <td>{link(r.origin)}</td>
          <td>{money(r.amount + r.fee_requested)} ({money(r.fee_requested)})</td>
          <td>{money(r.sent)}</td><td>{money(r.fee)}</td><td>{money(r.credited)}</td>
          <td>{r.refunded ? money(r.refunded) : "—"}</td>
          <td>{words(r.status)} · turn {r.turn}</td>
        </tr>)}</tbody>
      </table></div>}
    {record.receipts_dropped ? <p className="systems-note">{record.receipts_dropped} more rows are counted but not listed.</p> : null}
    {t ? <p className="systems-note">This turn: {money(t.debited_milli)} left senders = {money(t.credited_milli)} credited + {money(t.fee_milli)} in fees{t.refunded_milli ? `; ${money(t.refunded_milli)} was refunded` : ""}.</p> : null}
    {record.unmet && record.unmet.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Unmet senders at snapshot ${turn}`}>
        <thead><tr><th>Migrant</th><th>Left</th><th>Lives in</th><th>Why no recipient</th><th>Wealth above the reserve</th></tr></thead>
        <tbody>{record.unmet.map((u) => <tr key={u.id}>
          <td>#{u.id}</td><td>{link(u.origin)}</td><td>{link(u.destination)}</td>
          <td>{UNMET_NOTE[u.reason]}</td><td>{money(u.surplus_milli)}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.unmet_dropped ? <p className="systems-note">{record.unmet_dropped} more unmet senders are counted but not listed.</p> : null}
    {record.regions && record.regions.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Diaspora by region at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Departures (skilled)</th><th>Arrivals (skilled)</th><th>Returns home</th><th>Diaspora abroad (skilled)</th><th>Migrants living here (skilled)</th><th>Received</th><th>Sent out (fees)</th></tr></thead>
        <tbody>{record.regions.map((r) => <tr key={r.region}>
          <td>{link(r.region)}</td>
          <td>{r.departures} ({r.qualified_departures})</td>
          <td>{r.arrivals} ({r.qualified_arrivals})</td>
          <td>{r.returns_home}</td>
          <td>{r.diaspora_out} ({r.qualified_out})</td>
          <td>{r.diaspora_in} ({r.qualified_in})</td>
          <td>{r.recipients ? `${money(r.inflow_milli)} to ${r.recipients}` : "—"}</td>
          <td>{r.senders ? `${money(r.outflow_milli)} from ${r.senders} (${money(r.fee_milli)})` : "—"}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.closures && record.closures.length > 0 ? <p className="systems-note">Ledger entries closed this turn: {record.closures.map((c) =>
      `#${c.id} ${words(c.reason)} (left ${name(c.origin)} in turn ${c.departure_turn}, last in ${name(c.destination)})`).join("; ")}{record.closures_dropped ? `; ${record.closures_dropped} more` : ""}.</p> : null}
    {record.moves && record.moves.length > 0 ? <p className="systems-note">Moves this turn: {record.moves.map((m) =>
      `#${m.id} ${name(m.from_region)} → ${name(m.to_region)} (${words(m.kind)}${m.qualified ? ", qualified" : ""})`).join("; ")}{record.moves_dropped ? `; ${record.moves_dropped} more` : ""}.</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Diaspora lifetime counts at snapshot ${turn}`}>
      <thead><tr><th>Diaspora (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{diasporaCounts(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}</tbody>
    </table></div>
    {record.last_pool_reset ? <p className="systems-note">The native pool was rebuilt in turn {record.last_pool_reset.turn}: {record.last_pool_reset.entries_closed} ledger entries were closed ({record.last_pool_reset.reason}).</p> : null}
  </section>;
}
