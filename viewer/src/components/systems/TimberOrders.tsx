import type { SystemPanelProps } from "../../lib/systems";
import { timberOrdersAt } from "../../lib/timberOrders";
const show = (n: number) => (n / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
/** Real cargo and escrow, never inferred from demand or budget envelopes. */
export function TimberOrders({ bundle, snapshot, onSelectRegion }: SystemPanelProps) {
  const regions = bundle.world_state.regions, r = timberOrdersAt(snapshot, regions.length, bundle.world_state.civilizations?.length ?? 0);
  if (r.status === "absent") return null;
  const link = (id: number) => <button type="button" className="systems-link" onClick={() => onSelectRegion(regions[id].name)}>{regions[id].name}</button>;
  return <section className="systems-section" aria-label="Timber orders"><h3>Timber orders</h3>
    {r.status === "malformed" || !r.record ? <p className="systems-note">Rejected timber order record: cargo, escrow, date or identity validation failed. No values shown.</p> : <>
      <p className="systems-note">Simulation turn {r.record.source_turn}. Merchants buy real free timber from the origin treasury. The destination funds a finite escrow; only delivered timber earns freight payment and enters the repair store. Lost or cancelled cargo earns no payment; unused escrow returns to its actual payer. Money and timber below are different units.</p>
      {r.record.frame === null ? <p className="systems-note">Completed-turn activity unknown, not zero.</p> : <p className="systems-note">{r.record.frame.events.length} recorded events{r.record.frame.events_dropped ? `; ${r.record.frame.events_dropped} more dropped (absence is not proof of no activity)` : ""}.</p>}
      {r.record.orders.length + r.record.closed.length === 0 ? <p className="systems-note">No live or retained recent order (recorded zero; older closed orders may have expired from retention).</p> : <div className="systems-table-wrap"><table className="systems-table" aria-label="Timber cargo and escrow"><thead><tr><th>Order / carrier</th><th>Route / position</th><th>Outcome</th><th>Timber bought / aboard / delivered / lost / commons</th><th>Money paid origin / escrow held / credited / refunded</th></tr></thead><tbody>
        {[...r.record.orders, ...r.record.closed].map((o) => <tr key={o.id}><td>Timber order #{o.id}<br/>Person #{o.holder}</td><td>{link(o.origin)} → {link(o.dest)}<br/>Cargo at {link(o.path[o.cursor])}</td><td>{o.outcome ?? "moving"}<br/>Turn {o.closed_turn ?? o.dispatched_turn}</td><td>{[o.cargo_open_milli,o.cargo_milli,o.delivered_milli,o.lost_milli,o.deposited_milli].map(show).join(" / ")}</td><td>{[o.purchase_milli,o.cash,o.credited_milli,o.refunded_milli].map(show).join(" / ")}<br/>Escrow funded {show(o.escrowed_milli)}</td></tr>)}
      </tbody></table></div>}
      <p className="systems-note">Carrier ordinary income withheld is recorded separately from freight credits. Cancellation deposits surviving timber in the commons where the cargo stands; the merchant bears its unrecovered purchase cost. A treasury promise or dispatch is not a delivery.</p>
    </>}
  </section>;
}
