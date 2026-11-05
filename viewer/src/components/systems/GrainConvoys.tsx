import type { Bundle, TurnSnapshot } from "../../types";
import {
  convoyFunnel, hasGrainConvoysRecord, readGrainConvoys,
  type GrainConvoyRow, type GrainConvoyTransition,
} from "../../lib/grainConvoys";

const show = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));
const percent = (n: number) => `${Math.round(n * 100)}%`;
const STATUS: Record<string, string> = { en_route: "On the road", waiting: "Waiting", returning: "Turning back" };
const OPERATION: Record<string, string> = {
  dispatched: "Dispatched (paid)", advanced: "Advanced", waited: "Waited (road closed)",
  turned_back: "Turned back", arrived: "Delivered to granary", captured: "Captured", lost: "Lost",
  returned: "Back at origin market", stranded: "Stranded",
};

function placeName(bundle: Bundle | undefined, index: number): string {
  return bundle?.world_state?.regions?.[index]?.name ?? `Region ${index}`;
}

function routeText(row: GrainConvoyRow): string {
  return row.route.map((r, i) => {
    const label = row.route_names[i] ?? `Region ${r}`;
    return i === row.leg ? `[${label}]` : label;
  }).join(" → ");
}

function note(row: GrainConvoyTransition, bundle: Bundle | undefined): string {
  const parts: string[] = [];
  if (row.rerouted) parts.push("rerouted");
  if (row.closure) parts.push(`closed road: ${row.closure.replace(/_/g, " ")}`);
  if (row.threat) parts.push(`threat: ${row.threat.replace(/_/g, " ")}${row.threat_risk === null ? "" : ` (${percent(row.threat_risk)} then)`}${row.repelled ? ", beaten off by escort" : ""}`);
  if (row.operation === "arrived" && row.keeper !== null) {
    parts.push(row.keeper === row.buyer ? "kept by the buyer" : row.keeper < 0 ? "granary without a keeper" : `kept by civilization ${row.keeper}, not the buyer`);
  }
  if (row.sink) parts.push(`went to: ${row.sink.replace(/_/g, " ")}${row.sink_region === null ? "" : ` (${placeName(bundle, row.sink_region)})`}`);
  if (row.operation === "dispatched") parts.push(`paid ${row.paid} to the seller${row.escort_fee ? `, ${row.escort_fee} escort fee (public cost, no recipient)` : ", no escort"}`);
  return parts.join("; ") || "—";
}

/** Grain convoys at one snapshot: dated, bounded and never inferred from the final world. */
export function GrainConvoys({ snapshot, bundle }: { snapshot: TurnSnapshot | null; bundle?: Bundle }) {
  const record = readGrainConvoys(snapshot);
  if (!record) {
    return <div aria-label="Grain convoys">
      <h4>Grain convoys</h4>
      <p className="systems-note">{hasGrainConvoysRecord(snapshot)
        ? "This snapshot's convoy record could not be read (wrong turn, version or shape); nothing is shown rather than a guess."
        : `No convoy record at ${snapshot ? `snapshot ${snapshot.turn}` : "this point"}. Absent is not zero: the switch may have been off or idle.`}</p>
    </div>;
  }
  const f = convoyFunnel(record);
  const turn = record.source_turn;
  return <div aria-label="Grain convoys">
    <h4>Grain convoys after simulation turn {turn}</h4>
    <p className="systems-note"><strong>New convoys {record.enabled ? "accepted" : "paused (draining)"}</strong>; route choice: {record.route_policy}.
      {" "}Paid at dispatch; cargo is buyer-titled and feeds nobody until a granary opening releases it.
      {" "}{show(record.in_transit_cargo)} grain is heading for granaries{record.returning_cargo > 0 ? `, ${show(record.returning_cargo)} is turning back` : ""}.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Convoy activation up to simulation turn ${turn}`}>
      <thead><tr><th>Eligible deficits</th><th>Dispatched</th><th>Delivered</th><th>Captured</th><th>Lost</th><th>Returned</th><th>Stranded</th><th>On the road</th></tr></thead>
      <tbody><tr><td>{f.eligible}</td><td>{f.dispatched}</td><td>{f.arrived} ({show(f.delivered)} grain)</td><td>{f.captured}</td><td>{f.lost}</td><td>{f.returned}</td><td>{f.stranded}</td><td>{f.onRoad}</td></tr></tbody>
    </table></div>
    <p className="systems-note">Not dispatched: {f.noBudget} without budget, {f.noRoute} without an open route, {f.unaffordable} worth less than one treasury, {f.refused} at capacity.
      {" "}Escorts: {f.escorted} paid ({f.escortPaid} treasury), {f.escortWasted} met no threat.</p>
    {record.active.length === 0 ? <p className="systems-note">No convoy on the road after turn {turn}.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Convoys on the road after simulation turn ${turn}`}>
        <thead><tr><th>Convoy</th><th>Buyer / seller</th><th>Route (position)</th><th>Leg</th><th>Status</th><th>Cargo</th><th>Escort</th></tr></thead>
        <tbody>{record.active.map((row) => <tr key={row.convoy}>
          <td>{row.id}</td>
          <td>{row.buyer_name} / {row.seller_name}</td>
          <td>{routeText(row)}</td>
          <td>{row.progress === 0 ? `at stop ${row.leg + 1} of ${row.route.length}` : `edge ${row.leg + 1}, turn ${row.progress} of ${row.leg_turns}`}</td>
          <td>{STATUS[row.status]}{row.waits ? ` (${row.waits} turn${row.waits === 1 ? "" : "s"} blocked)` : ""}</td>
          <td>{show(row.cargo)}</td>
          <td>{row.escorted ? `Yes, ${row.escort_fee} paid` : "No"} · dispatch risk {percent(row.escorted ? row.escorted_risk : row.exposed_risk)}</td>
        </tr>)}</tbody>
      </table></div>}
    {record.transitions === null
      ? <p className="systems-note">What convoys did in turn {turn} was not recorded (unknown, not zero).</p>
      : record.transitions.length === 0 ? <p className="systems-note">No convoy was dispatched or moved in turn {turn}.</p>
        : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Convoy movements in turn ${turn}`}>
          <thead><tr><th>Convoy</th><th>What happened</th><th>Where</th><th>Cargo</th><th>Notes</th></tr></thead>
          <tbody>{record.transitions.map((row) => <tr key={`${row.id}:${row.operation}`}>
            <td>{row.id}</td><td>{OPERATION[row.operation]}</td><td>{row.at_name}</td><td>{show(row.cargo)}</td><td>{note(row, bundle)}</td>
          </tr>)}</tbody>
        </table></div>}
  </div>;
}
