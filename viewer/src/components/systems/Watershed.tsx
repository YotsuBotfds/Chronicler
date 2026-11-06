import { useMemo, type ReactNode } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import { drainsTo, readWatershed, readWatershedRun, watershedOutflow } from "../../lib/watershed";
import type { WatershedDrought, WatershedRecord, WatershedStatic } from "../../watershedTypes";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
/** A signed difference at display precision ("0", never "-0"). */
const signed = (value: number) => Math.abs(value) < 0.0005 ? "0" : `${value > 0 ? "+" : ""}${show(value)}`;

// Short row names (the label column does not wrap on a phone); the note under the header explains them.
const TOTALS: Array<[keyof NonNullable<WatershedRecord["totals"]>, string]> = [
  ["precipitation", "Precipitation"],
  ["external_in", "External inflow"],
  ["external_out", "External outflow"],
  ["evaporation", "Evaporation"],
  ["withdrawal", "Irrigation withdrawal"],
  ["to_sea", "Outflow to the sea"],
  ["to_sink", "Closed-basin loss"],
  ["to_lake", "Outflow to lakes"],
  ["transfer", "Passed downstream"],
];
const COUNTERS: Array<[string, string]> = [
  ["settled_turns", "Settled turns"], ["abandoned_plans", "Dropped plans (failed tick)"],
  ["flood_region_turns", "Flooded region-turns"], ["drought_region_turns", "Region-turns in drought"],
  ["droughts_declared", "Droughts declared"], ["droughts_ended", "Droughts ended"],
  ["external_out_unmet_turns", "Turns with unmet outflow"],
  ["stale_baseline_turns", "Turns with a stale baseline"],
  ["flood_consequences", "Floods that acted (flow)"],
  ["superseded_river_floods", "River floods superseded (flow)"],
];

/** Completed-turn watershed accounts only; never reads final-world state. */
export function Watershed({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const names = regions.map((region) => region.name);
  const run = useMemo(() => readWatershedRun(bundle.history), [bundle]);
  const reading = readWatershed(snapshot, regions.length, run);
  const at = snapshot?.turn ?? currentTurn;
  const regionLink = (rid: number) => <button type="button" className="systems-link"
    onClick={() => onSelectRegion(names[rid])}>{names[rid]}</button>;
  const mode = reading.status === "ok" || reading.status === "unobserved" ? reading.record.mode : null;
  const header = <>
    <h3>Watershed account · snapshot {at}</h3>
    {mode === "flow"
      ? <p className="systems-note">Flow: the account's derived index is the water index the simulation used. The native climate water terms, the irrigation water bonus and the downstream deforestation cascade are switched off; upstream irrigation withdrawals reduce the water downstream, and the account's floods act on the capacity modifier, the soil and the flood cooldown. The old river flood still draws from the shared environment stream, but its effect is superseded (listed below). Water in water units (wu: one region's storage capacity without forest cover is 1).</p>
      : <p className="systems-note">{mode === "record_only" ? "Record only: a" : "A"} conserved water account on the drainage graph of this procedural world {mode === "record_only" ? "runs beside the water index the simulation uses and changes nothing" : "(record only or flow)"}. Its constants are fitted to the old index's cycle on development worlds; in record only, a gap between the index it would derive and the index used is a calibration observation, not an effect. Water in water units (wu: one region's storage capacity without forest cover is 1).</p>}
    <p className="systems-note">Precipitation includes tundra melt; evaporation includes transpiration; irrigation withdrawal is consumed. External inflow and outflow are changes of the water index between ticks made by other writers, attributed to a coastal flood where one struck and otherwise left unattributed. A closed basin (sink) or a lake loses what reaches it; water passed downstream stays in the account. Each region's outflow is the residual of its account, so closure holds by construction: the residual shows the routing and arithmetic are intact, not that the model is right.</p>
  </>;
  if (reading.status !== "ok" && reading.status !== "unobserved") {
    const text = reading.status === "disabled" ? "The watershed account is off in this run (--watershed not recorded)."
      : reading.status === "absent" ? `No watershed record at snapshot ${at}, although the run records it elsewhere: this turn's account is unknown.`
      : `The watershed record at snapshot ${at} is malformed (${reading.reason}); nothing is shown from it.`;
    return <section className="systems-section" aria-label="Watershed">{header}<p className="systems-note">{text}</p></section>;
  }
  const record = reading.record;
  const statics = reading.statics;
  const cumulative = record.cumulative;
  return <section className="systems-section" aria-label="Watershed">
    {header}
    <p className="systems-note">Opened at turn {record.opened_turn}; the graph reproduces {statics.graph.river_steps} saved river step{statics.graph.river_steps === 1 ? "" : "s"}. Each region drains to one place: its lowest lower neighbour, the sea, a lake or a closed basin.</p>
    {reading.status === "unobserved"
      ? <p className="systems-note">No Phase 9 account was settled in simulation turn {record.source_turn}; this turn's flows, floods and droughts are unknown, not zero.</p>
      : <Settled record={record} statics={statics} names={names} regionLink={regionLink} />}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Water account since turn ${record.opened_turn}`}><tbody>
      <tr><th scope="row">Storage, opening → now</th><td>{show(cumulative.opening_storage)} → {show(cumulative.storage)}</td></tr>
      {TOTALS.map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{show(cumulative[key])}</td></tr>)}
      <tr><th scope="row">Closure residual</th><td>{cumulative.closure_residual?.toExponential(1) ?? "Unknown"}</td></tr>
    </tbody></table></div>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Watershed counters to snapshot ${at}`}><tbody>
      {COUNTERS.filter(([key]) => key in record.counters).map(([key, label]) =>
        <tr key={key}><th scope="row">{label}</th><td>{show(record.counters[key])}</td></tr>)}
    </tbody></table></div>
  </section>;
}

function Settled({ record, statics, names, regionLink }: {
  record: WatershedRecord; statics: WatershedStatic; names: string[]; regionLink: (rid: number) => ReactNode;
}) {
  const c = record.regions!;
  const t = record.totals!;
  const outflow = watershedOutflow(record)!;
  const turn = record.completed_turn;
  const flow = record.mode === "flow";
  const declared = new Set(record.droughts!.declared.map((d) => d.region));
  const droughts: Array<[WatershedDrought, string]> = [
    ...record.droughts!.declared.map((d): [WatershedDrought, string] => [d, "Declared this turn"]),
    ...record.droughts!.ended.map((d): [WatershedDrought, string] => [d, `Ended at turn ${d.end_turn}`]),
  ];
  const stillOpen = record.droughts!.open.filter((d) => !declared.has(d.region));
  const sourceText = (source: string) => source === "coastal_flood" ? "coastal flood" : "unattributed";
  return <>
    <p className="systems-note">Phase 9 of simulation turn {record.source_turn}, climate phase {record.phase}.</p>
    {record.stale_baseline ? <p className="systems-note">Stale baseline: the index was not observed after the previous tick (a dropped plan or a missing turn), so this turn's external flows include unsettled changes and are all unattributed.</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Water account at snapshot ${turn}`}><tbody>
      {TOTALS.map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{show(t[key])}</td></tr>)}
      <tr><th scope="row">Storage, open → close</th><td>{show(t.storage_open)} → {show(t.storage_close)}</td></tr>
      <tr><th scope="row">Closure residual</th><td>{t.closure_residual.toExponential(1)}</td></tr>
      {t.external_out_unmet > 0 ? <tr><th scope="row">Unmet external outflow</th><td>{show(t.external_out_unmet)}</td></tr> : null}
    </tbody></table></div>
    {record.external!.length > 0 && <div className="systems-table-wrap"><table className="systems-table" aria-label={`External flows at snapshot ${turn}`}>
      <thead><tr><th>Region</th><th>Direction</th><th>Source</th><th>Amount</th></tr></thead>
      <tbody>{record.external!.map((e) => <tr key={`${e.region}:${e.direction}:${e.source}`}>
        <td>{regionLink(e.region)}</td><td>{e.direction === "in" ? "Inflow" : "Outflow"}</td><td>{sourceText(e.source)}</td><td>{show(e.amount)}</td>
      </tr>)}</tbody>
    </table></div>}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Watershed regions at snapshot ${turn}`}>
      <thead><tr><th>Region</th><th>Drains to</th><th>Storage / capacity</th><th>Index used</th><th>Index derived</th>
        <th>Derived − used</th><th>Inflow</th><th>Outflow</th><th>Irrigation</th><th>Flood excess</th><th>Dry turns</th></tr></thead>
      <tbody>{names.map((_, rid) => <tr key={rid}>
        <td>{regionLink(rid)}</td><td>{drainsTo(statics.graph.down[rid], names)}</td>
        <td>{show(c.storage[rid])} / {show(c.capacity[rid])}</td><td>{show(c.index_observed[rid])}</td>
        <td>{show(c.index_derived[rid])}</td><td>{signed(c.index_derived[rid] - c.index_observed[rid])}</td>
        <td>{show(c.inflow[rid])}</td><td>{show(Math.max(0, outflow[rid]))}</td><td>{show(c.withdrawal[rid])}</td>
        <td>{show(c.flood_excess[rid])}</td><td>{c.drought_turns[rid]}</td>
      </tr>)}</tbody>
    </table></div>
    {record.floods!.length === 0 ? <p className="systems-note">No region's arrivals exceeded its channel this turn (recorded: no flood).</p>
      : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Floods at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Excess</th><th>Arrivals = rain + inflow + external</th><th>Channel</th><th>Tributaries (outflow)</th><th>Upstream cover</th>{flow ? <th>What it did</th> : null}</tr></thead>
        <tbody>{record.floods!.map((f) => <tr key={f.region}>
          <td>{regionLink(f.region)}</td><td>{show(f.excess)}</td>
          <td>{show(f.arrivals)} = {show(f.precipitation)} + {show(f.inflow)} + {show(f.external_in)}</td><td>{show(f.channel)}</td>
          <td>{f.tributaries.length === 0 ? "None (headwater)" : f.tributaries.map(([u, q]) => `${names[u]} ${show(q)}`).join("; ")}</td>
          <td>{f.upstream_cover === null ? "No upstream region" : `${show(f.upstream_cover)} mean; ${f.upstream_deforested} deforested`}</td>
          {flow ? <td>{f.consequence ? `capacity ×${show(f.consequence.capacity_modifier)}; cooldown ${f.consequence.cooldown} turns; soil ${show(f.consequence.soil_before)} → ${show(f.consequence.soil_after)}` : "Unknown"}</td> : null}
        </tr>)}</tbody>
      </table></div>}
    {flow && (record.superseded!.length === 0
      ? <p className="systems-note">No river flood was superseded this turn (recorded: none).</p>
      : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Superseded river floods at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Old river flood (suppressed)</th></tr></thead>
        <tbody>{record.superseded!.map((e) => <tr key={e.region}>
          <td>{regionLink(e.region)}</td><td>drew a {e.duration}-turn flood; its capacity, cooldown and silt were not applied</td>
        </tr>)}</tbody>
      </table></div>)}
    {droughts.length === 0 && stillOpen.length === 0 ? <p className="systems-note">No region is in a declared drought this turn (recorded: none).</p>
      : droughts.length === 0 ? null
      : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Droughts at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Status</th><th>Since turn</th><th>Turns</th><th>Lowest fill</th><th>Rain vs normal (difference)</th><th>Inflow</th><th>Irrigation own · upstream</th><th>Upstream cover</th></tr></thead>
        <tbody>{droughts.map(([d, status]) => <tr key={`${d.region}:${status}`}>
          <td>{regionLink(d.region)}</td><td>{status}</td><td>{d.start_turn}</td><td>{d.turns}</td><td>{show(d.min_fraction)}</td>
          <td>{show(d.precipitation)} vs {show(d.normal_precipitation)} ({signed(d.precipitation - d.normal_precipitation)})</td>
          <td>{show(d.inflow)}</td><td>{show(d.withdrawal)} · {show(d.upstream_withdrawal)}</td>
          <td>{d.upstream_cover === null ? "No upstream region" : show(d.upstream_cover)}</td>
        </tr>)}</tbody>
      </table></div>}
    {stillOpen.length > 0 && <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open droughts at snapshot ${turn}`}>
      <thead><tr><th>Region</th><th>Since turn</th><th>Declared</th><th>Turns</th><th>Lowest fill</th></tr></thead>
      <tbody>{stillOpen.map((d) => <tr key={d.region}>
        <td>{regionLink(d.region)}</td><td>{d.start_turn}</td><td>turn {d.declared_turn}</td><td>{d.turns}</td><td>{show(d.min_fraction)}</td>
      </tr>)}</tbody>
    </table></div>}
    {stillOpen.length > 0 && <p className="systems-note">An open drought's conditions are recorded in full in the snapshot of the turn it was declared and in the one it ends.</p>}
  </>;
}
