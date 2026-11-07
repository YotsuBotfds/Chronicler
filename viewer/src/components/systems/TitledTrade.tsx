import type { ReactNode } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import { GOODS, titledTradeAt, tradeFunnel, units, type ShipmentRecord } from "../../lib/titledTrade";

const show = (value: number | null | undefined) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const food = (milli: number) => show(units(milli));
const OUTCOME: Record<string, string> = {
  delivered: "delivered (the holder's retail claim at the destination)",
  returned: "returned to the origin at full value",
  escheated: "holder died: cargo to the commons where it stood",
  pool_reset: "native pool rebuilt: cargo to the commons where it stood",
  switched_off: "titled trade switched off: cargo to the commons where it stood",
};
const CAUSE: Record<string, string> = {
  destination_conquered: "destination conquered", quarantine_closure: "quarantine closed the route",
  route_lost: "no route left", destination_left_pilot: "destination left the retail pilot",
};
const RELEASE: Record<string, string> = {
  migrated: "migrated", occupation: "changed occupation", enlisted: "enlisted", on_trip: "on a merchant trip",
  other_work: "held other work",
};

function cargo(milli: number[]): string {
  const parts = milli.map((v, g) => (v ? `${food(v)} ${GOODS[g]}` : null)).filter(Boolean);
  return parts.length ? parts.join(", ") : "none";
}

/** Completed-turn A4 titled trade records only; never reads final-world state. */
export function TitledTrade({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const at = snapshot?.turn ?? currentTurn;
  const { status, record } = titledTradeAt(snapshot, regions.length);
  const title = <h3>Titled trade{record ? ` · snapshot ${record.source_turn + 1}` : ""}</h3>;
  const wrap = (body: ReactNode) => <section className="systems-section" aria-label="Titled trade">{title}{body}</section>;
  if (status === "absent") return wrap(<p className="systems-note">No titled trade record at snapshot {at}.</p>);
  if (status === "disabled") return wrap(<p className="systems-note">Titled trade is off at snapshot {at}: merchants carry only the commons, and owned food never leaves its region.</p>);
  if (status === "malformed" || record === null) return wrap(<p className="systems-note">The titled trade record at snapshot {at} is malformed or its books do not close; nothing is shown from it.</p>);
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const link = (index: number) => <button type="button" className="systems-link" onClick={() => onSelectRegion(region(index))}>{region(index)}</button>;
  const f = tradeFunnel(record);
  const frame = record.frame;
  const position = (s: ShipmentRecord) => s.cursor === 0 ? `at ${region(s.origin)} (leaves next turn)`
    : `at ${region(s.path[s.cursor])}, ${s.path.length - 1 - s.cursor} hop(s) to go`;
  return <section className="systems-section" aria-label="Titled trade">
    {title}
    <p className="systems-note">Simulation turn {record.source_turn}. A merchant buys owners' food above their reserve, pro rata, at the local retail price, paying each owner directly; it holds title to the cargo while it travels one region a turn (its own merchant income withheld meanwhile), and the delivered cargo becomes its retail claim, sold to the destination's households. Food in food units, money in units of a person's wealth.</p>
    {frame === null ? <p className="systems-note">No titled trade pass was recorded in simulation turn {record.source_turn}; purchases, moves and sales are unknown, not zero.</p> : null}
    {record.shipments.length === 0 ? <p className="systems-note">No shipment was in transit after simulation turn {record.source_turn} (a recorded zero).</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Shipments in transit at snapshot ${record.source_turn + 1}`}>
        <thead><tr><th>Shipment</th><th>Holder (title)</th><th>Carrier</th><th>Route</th><th>Position</th><th>Cargo aboard</th><th>Paid owners</th><th>Income withheld</th></tr></thead>
        <tbody>{record.shipments.map((s) => <tr key={s.id}>
          <td>#{s.id} (bought turn {s.dispatched_turn})</td>
          <td>{s.holder}</td>
          <td>{s.carrier === null ? `released${s.released ? ` (${RELEASE[s.released] ?? s.released})` : ""}` : `${s.carrier} (reserved)`}</td>
          <td>{link(s.origin)} → {link(s.dest)}</td>
          <td>{position(s)}</td>
          <td>{cargo(s.cargo)}</td>
          <td>{show(units(s.cost_milli))} to {show(s.sellers)} owner(s)</td>
          <td>{show(s.withheld)} over {show(s.withheld_turns)} turn(s)</td>
        </tr>)}</tbody>
      </table></div>}
    {frame !== null && frame.dispatched.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Purchases from owners in simulation turn ${record.source_turn}`}>
      <thead><tr><th>Shipment</th><th>Owners → merchant</th><th>Food bought</th><th>Price per ration</th><th>Paid (by id)</th></tr></thead>
      <tbody>{frame.dispatched.map((d) => <tr key={d.shipment}>
        <td>#{d.shipment}: {link(d.origin)} → {link(d.dest)}</td>
        <td>{d.seller_rows.map((r) => `${r[0]}: ${food(r[1])}`).join("; ")}{d.sellers > d.seller_rows.length ? ` and ${d.sellers - d.seller_rows.length} more` : ""} → {d.holder}</td>
        <td>{cargo(d.cargo)}</td>
        <td>{show(units(d.price_milli))}</td>
        <td>{show(units(d.paid))}{d.refunded ? ` (${show(units(d.refunded))} refused by a ceiling, kept by the merchant)` : ""}</td>
      </tr>)}</tbody>
    </table></div> : frame !== null ? <p className="systems-note">No merchant bought owned food in simulation turn {record.source_turn} (a recorded zero).</p> : null}
    {frame !== null && frame.events.some((e) => e.event !== "moved") ? <ul className="systems-note" aria-label="Shipment outcomes">
      {frame.events.filter((e) => e.event !== "moved").map((e, i) => <li key={`${e.shipment}-${i}`}>
        Shipment #{e.shipment}: {e.event === "carrier_released" ? `carrier released (${RELEASE[e.reason ?? ""] ?? e.reason}); the holder keeps title` : `${OUTCOME[e.event] ?? e.event}${e.cause ? `, because the ${CAUSE[e.cause] ?? e.cause}` : ""}`} at {region(e.region)}{e.delivered ? `; ${food(e.delivered)} delivered` : ""}{e.returned ? `; ${food(e.returned)} returned` : ""}{e.deposited ? `; ${food(e.deposited)} to the commons` : ""}.
      </li>)}
    </ul> : null}
    {frame !== null && frame.sales.length > 0 ? <p className="systems-note">Holders' sales of delivered cargo this turn: {frame.sales.map((s) => `${s.holder} sold ${food(s.cargo_sold)} at ${region(s.region)} for ${show(units(s.credited))}${s.exact ? "" : " (approximate)"}`).join("; ")}.</p> : null}
    <table className="systems-table" aria-label={`Titled trade funnel to snapshot ${record.source_turn + 1}`}>
      <tbody>
        <tr><th scope="row">Shipments bought · delivered · returned · escheated · ended</th><td>{`${show(f.dispatched)} · ${show(f.delivered)} · ${show(f.returned)} · ${show(f.escheated)} · ${show(f.ended)}`}</td></tr>
        <tr><th scope="row">Returned because</th><td>{Object.entries(f.returnedBy).filter(([, n]) => n).map(([k, n]) => `${CAUSE[k] ?? k} ${n}`).join("; ") || "—"}</td></tr>
        <tr><th scope="row">Food bought from owners · paid to them</th><td>{`${show(f.bought)} · ${show(f.paid)}`}</td></tr>
        <tr><th scope="row">Lost in transit (decay · sea) · delivered · returned · to the commons</th><td>{`${show(f.transitDecay)} · ${show(f.seaLoss)} · ${show(f.consigned)} · ${show(f.returnedFood)} · ${show(f.deposited)}`}</td></tr>
        <tr><th scope="row">Delivered food sold to households · credited to holders</th><td>{`${show(f.cargoSold)} · ${show(f.salesCredited)}${f.salesInexact ? ` (${show(f.salesInexact)} approximate)` : ""}`}</td></tr>
        <tr><th scope="row">Merchants' net money (sales credited − paid to owners)</th><td>{show(f.netMoney)}</td></tr>
        <tr><th scope="row">Merchant income withheld while carrying · carrier-turns · carriers released</th><td>{`${show(f.withheld)} · ${show(f.carrierTurns)} · ${show(f.carriersReleased)}`}</td></tr>
      </tbody>
    </table>
    {record.closed.length > 0 ? <p className="systems-note">Recent shipments: {record.closed.slice(-6).map((s) => `#${s.id} ${region(s.origin)} → ${region(s.dest)}: ${s.outcome}${s.cause ? ` (${CAUSE[s.cause] ?? s.cause})` : ""}, turn ${s.closed_turn}`).join("; ")}.</p> : null}
  </section>;
}
