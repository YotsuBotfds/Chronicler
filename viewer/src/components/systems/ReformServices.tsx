import type { ReactNode } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import {
  readReformServices, reliefByRegion, reliefRecordAt, type ReliefFrame,
} from "../../lib/reformServices";

const units = (milli: number) => (milli / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const PATH_LABEL: Record<string, string> = {
  upkeep: "the relief's upkeep", institution: "Commons Management's share of the enforcement payment",
};

/** The completed turn's poor-relief services record only; never reads final-world state. */
export function ReformServices({ bundle, snapshot, currentTurn }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readReformServices(bundle, snapshot, currentTurn);
  const at = snapshot?.turn ?? currentTurn;
  const record = reading.record;
  const heading = <h3>Poor relief services{record !== null ? ` · snapshot ${record.source_turn + 1}` : ""}</h3>;
  const section = (body: ReactNode) =>
    <section className="systems-section" aria-label="Poor relief services">{heading}{body}</section>;
  if (reading.state === "disabled") {
    return section(<p className="systems-note">Poor relief services are off in this run (--reform-services not recorded): a granted poor relief credits every agent's material need for grievance and its upkeep is sunk.</p>);
  }
  if (reading.state === "absent") {
    return section(<p className="systems-note">No poor-relief services record at snapshot {at}: unknown, not zero.</p>);
  }
  if (reading.state === "malformed") {
    const why = reliefRecordAt(snapshot, regions.length, civs.length).reason ?? "unreadable";
    return section(<p className="systems-note">The poor-relief services record at snapshot {at} was rejected as malformed: {why}. Nothing is shown from it.</p>);
  }
  const r = reading.record!;   // the three readings without a record returned above
  if (reading.state === "unobserved") {
    return section(<p className="systems-note">Simulation turn {r.source_turn} was not observed: relief payments and purchases that turn are unknown, not zero.</p>);
  }
  const control = r.mode === "cost_only";
  const intro = <p className="systems-note">Simulation turn {r.source_turn}, mode {r.mode}. {control
    ? "The cost-only control: a granted poor relief no longer credits anyone's need, and its payment is sunk as without the switch; nothing is bought."
    : "A granted poor relief no longer credits anyone's need; the treasury's relief payment goes into the realm's relief fund (up to four turns of upkeep, the rest sunk), which buys owners' unsold food, paid by stable id, where the realm's own retail markets recorded people below a full ration. The food joins the commons the next free rations draw on, so what reached people is bounded per region, never attributed to persons."}</p>;
  if (reading.state === "recorded_zero") {
    return section(<>{intro}<p className="systems-note">Nothing moved this turn: no relief money was paid in, spent or returned, and nothing was bought or delivered (recorded zero).</p></>);
  }
  const name = (i: number) => civs[i]?.name ?? `Civ ${i}`;
  const region = (i: number) => regions[i]?.name ?? `Region ${i}`;
  return section(<>{intro}<Frame frame={r.frame!} source={r.source_turn} civName={name} regionName={region} /></>);
}

function Frame({ frame, source, civName, regionName }: {
  frame: ReliefFrame; source: number; civName: (i: number) => string; regionName: (i: number) => string;
}) {
  const byRegion = reliefByRegion(frame);
  return <>
    {frame.civs.length === 0 ? <p className="systems-note">No realm held a relief or a fund this turn (recorded zero).</p>
      : <table className="systems-table" aria-label={`Relief funds at snapshot ${source + 1}`}>
        <thead><tr><th>Realm</th><th>Paid in from</th><th>Fund at start</th><th>Paid in</th><th>Sunk</th>
          <th>Spent on food</th><th>Returned to treasury</th><th>Fund at end</th><th>Cap</th></tr></thead>
        <tbody>{frame.civs.map((c) => <tr key={c.civ}>
          <td>{civName(c.civ)}</td>
          <td>{c.path === null ? (c.reform === null ? "relief ended" : "nothing this turn") : PATH_LABEL[c.path]}</td>
          <td>{units(c.fund_open_milli)}</td><td>{units(c.to_fund_milli)}</td><td>{c.sunk_units}</td>
          <td>{units(c.spent_milli)}{c.residual_milli ? ` (${units(c.residual_milli)} refused by a wealth ceiling, kept)` : ""}</td>
          <td>{units(c.refunded_milli)}</td><td>{units(c.fund_close_milli)}</td><td>{units(c.cap_milli)}</td>
        </tr>)}</tbody>
      </table>}
    {frame.purchases.length === 0 ? <p className="systems-note">No food was bought this turn (recorded zero).</p>
      : <table className="systems-table" aria-label={`Relief purchases at snapshot ${source + 1}`}>
        <thead><tr><th>Region</th><th>Realm</th><th>Unmet need (rations)</th><th>Ask per ration</th>
          <th>Food bought</th><th>Rations</th><th>Paid to owners</th><th>Sellers</th></tr></thead>
        <tbody>{frame.purchases.map((p) => <tr key={p.region}>
          <td>{regionName(p.region)}</td><td>{civName(p.civ)}</td><td>{show(p.unmet_rations)}</td>
          <td>{units(p.price_milli)}</td><td>{units(p.food_milli)}</td><td>{show(p.rations)}</td>
          <td>{units(p.credited_milli)}</td><td>{p.sellers}</td>
        </tr>)}</tbody>
      </table>}
    {frame.deliveries.length === 0 ? <p className="systems-note">No delivery was read this turn: nothing was bought last turn (recorded zero).</p>
      : <table className="systems-table" aria-label={`Relief deliveries at snapshot ${source + 1}`}>
        <thead><tr><th>Region</th><th>Bought at turn</th><th>Rations bought</th><th>Free pool (given / unallocated)</th>
          <th>Reached people (rations)</th><th>Priced out now</th></tr></thead>
        <tbody>{frame.deliveries.map((d) => <tr key={`${d.region}-${d.bought_turn}`}>
          <td>{regionName(d.region)}</td><td>{d.bought_turn}</td><td>{show(d.rations_bought)}</td>
          <td>{d.observed ? `${show(d.free_given)} / ${show(d.free_unallocated)}` : "unobserved (no provisioning): unknown, not zero"}</td>
          <td>{!d.observed ? "Unknown" : d.delivered_at_least === null
            ? `at most ${show(d.delivered_at_most)} (no lower bound: the commons covered demand)`
            : `${show(d.delivered_at_least)} to ${show(d.delivered_at_most)}`}</td>
          <td>{show(d.priced_out_persons, 0)}</td>
        </tr>)}</tbody>
      </table>}
    {byRegion.length > 0 ? <p className="systems-note">By region: {byRegion.map((r) =>
      `${regionName(r.region)} bought ${show(r.bought)} rations${r.atMost === null ? "" : `, delivered at most ${show(r.atMost)}`}${r.atLeast === null ? "" : `, at least ${show(r.atLeast)}`}`).join("; ")}.
      Recipients are not named: relief food is pooled with the commons.</p> : null}
  </>;
}
