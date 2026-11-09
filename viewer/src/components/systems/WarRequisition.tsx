import type { SystemPanelProps } from "../../lib/systems";
import { warRequisitionAt } from "../../lib/warRequisition";
import { show } from "./formatters";
const money = (n: number) => show(n / 1000);
/** Physical sources and liabilities remain distinct from food creation and spendable cash. */
export function WarRequisition({ bundle, snapshot, onSelectRegion }: SystemPanelProps) {
  const regions = bundle.world_state.regions, r = warRequisitionAt(snapshot, regions.length, bundle.world_state.civilizations?.length ?? 0);
  if (r.status === "absent") return null;
  const link = (id: number) => <button type="button" className="systems-link" onClick={() => onSelectRegion(regions[id].name)}>{regions[id].name}</button>;
  const f = r.record?.frame;
  return <section className="systems-section" aria-label="Army supply and restitution"><h3>Army supply and restitution</h3>
    {r.status === "malformed" || !r.record ? <p className="systems-note">Rejected requisition record: dates, physical allocations or restitution books do not validate. No values shown.</p> : <>
      <p className="systems-note">Simulation turn {r.record.source_turn ?? "unobserved"}; mode {r.record.mode}{r.status === "disabled" ? "; disabled" : ""}. Food is physical food units; one food supplies two carried rations. Requisition not carried by an existing army is destruction. Restitution claims are liabilities, not spendable household money. Timber seizure records custody and value without creating army rations.</p>
      {!f ? <p className="systems-note">No completed-turn observation: unknown, not zero.</p> : <>
        <p className="systems-note">{f.events.length} retained events{f.events_dropped ? `; ${f.events_dropped} dropped` : ""}. Outstanding claims {f.claims_open}, money due {money(f.claims_due_milli)}{f.claims_dropped ? `; ${f.claims_dropped} claim rows outside the retained sample` : ""}.</p>
        {f.events.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label="Army physical supply events"><thead><tr><th>Event</th><th>Region / identity</th><th>Physical food and rations</th></tr></thead><tbody>{f.events.map((e, i) => <tr key={i}><td>{e.kind}<br/>Source turn {e.source_turn}</td><td>{e.region !== undefined ? link(e.region) : "Region unrecorded"}{e.army ? <><br/>Army {e.army}</> : null}{e.owner !== undefined ? <><br/>Owner #{e.owner}</> : null}{e.shipment !== undefined ? <><br/>{e.package === "timber_orders" ? "Timber order" : "Food shipment"} #{e.shipment}</> : null}</td><td>{e.removed_milli !== undefined ? <>Food removed {money(e.removed_milli)}; destroyed {money(e.destroyed_milli ?? 0)}<br/></> : null}{e.allocations?.map((a) => `${a.army}: ${show(a.rations)} rations`).join("; ")}{e.credited_rations !== undefined ? <>Credited {show(e.credited_rations)} rations</> : null}{e.kind === "consumption" ? <>Consumed {show(e.consumed_rations!)} of {show(e.demanded_rations!)} demanded rations; adequacy {show(e.adequacy!)}</> : null}{e.package === "timber_orders" ? <>Timber {money(e.quantity_milli ?? 0)}; acquisition-value liability {money(e.acquisition_value_milli ?? 0)} money</> : null}</td></tr>)}</tbody></table></div> : <p className="systems-note">No physical supply event recorded this turn (recorded zero).</p>}
        {f.claims.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label="Restitution liabilities"><thead><tr><th>Claim / owner</th><th>Region / source</th><th>Original due / actually paid / remaining</th><th>Status</th></tr></thead><tbody>{f.claims.map((c) => <tr key={c.id}><td>#{c.id}, person #{c.owner}<br/>Liable polity #{c.payer}</td><td>{link(c.region)}<br/>{c.source}, turn {c.turn}</td><td>{[c.due_milli,c.paid_milli,c.due_milli-c.paid_milli].map(money).join(" / ")}</td><td>{c.status}</td></tr>)}</tbody></table></div> : <p className="systems-note">No retained liability rows (recorded zero within retention).</p>}
      </>}
    </>}
  </section>;
}
