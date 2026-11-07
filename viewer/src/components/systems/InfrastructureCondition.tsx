import { useMemo } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import { conditionSeries, infrastructureOn, readInfrastructure, worksStory } from "../../lib/infrastructureCondition";
import type { InfraAsset, InfraConditionPoint, InfraReceipt, InfraWork } from "../../infrastructureConditionTypes";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const coins = (milli: number) => (milli / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const KIND: Record<string, string> = { irrigation: "Irrigation works", roads: "Road" };
const REASON: Record<string, string> = {
  no_timber: "no free timber", no_coins: "treasury short", no_labor: "not enough farm labour",
  no_envelope: "no repairs envelope", granary_first: "the granary held the labour",
};
const MODE_NOTE: Record<string, string> = {
  repair: "Repair mode: works restore condition with anonymous, unpaid farm labour, timber and treasury coins, planned after RS2's repairs and, under local budgets, only within their own envelope.",
  cost_only: "Cost-only control: works plan, hold timber, use labour and pay identically, but condition never rises.",
  wear_only: "Wear-only control: works wear and take damage and their service reaches irrigation and roads, but nothing repairs them.",
  record_only: "Record only: condition is tracked and recorded, but every consumer reads service 1.0 and no work opens; the run equals one without the switch.",
};
const CAUSE: Record<string, string> = {
  conquest: "Conquest", sack: "Sack", flood: "Flood (watershed flow, at its onset)",
};
const TIMBER: Record<string, string> = {
  supplied: "Covered by free timber and cargo on the way", expedition: "Waits for the region's live woodcutters",
  launched: "Woodcutters sent", refused: "No woodcutters",
};
const STATUS: Record<string, string> = {
  serving: "Serving", failed: "Failed (repair only)", inactive: "Inactive", destroyed: "Destroyed",
};

/** A small line of an asset's recorded condition (0 to 1) across the run up to this snapshot. */
function Trace({ points }: { points: InfraConditionPoint[] }) {
  if (points.length < 2) return <span>{points.length === 1 ? show(points[0].condition) : "Unknown"}</span>;
  const first = points[0].turn;
  const span = Math.max(1, points[points.length - 1].turn - first);
  const path = points.map((p) => `${((p.turn - first) / span * 60).toFixed(1)},${((1 - p.condition) * 14 + 1).toFixed(1)}`).join(" ");
  const label = `Condition ${show(points[0].condition)} at turn ${first} to ${show(points[points.length - 1].condition)} at turn ${points[points.length - 1].turn}`;
  return <svg width="62" height="16" viewBox="0 0 62 16" role="img" aria-label={label}>
    <title>{label}</title>
    <polyline points={path} fill="none" stroke="currentColor" strokeWidth="1.2" />
  </svg>;
}

/** Completed-turn infrastructure condition and works only; never reads final-world state. */
export function InfrastructureCondition({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const on = useMemo(() => infrastructureOn(bundle.history), [bundle]);
  const series = useMemo(() => conditionSeries(bundle.history, regions.length), [bundle, regions.length]);
  const at = snapshot?.turn ?? currentTurn;
  const story = useMemo(() => worksStory(bundle.history, regions.length, at), [bundle, regions.length, at]);
  const reading = readInfrastructure(snapshot, regions.length, on);
  const region = (index: number) => <button type="button" className="systems-link"
    onClick={() => onSelectRegion(regions[index]?.name ?? "")}>{regions[index]?.name ?? `Region ${index}`}</button>;
  const civ = (index: number) => index < 0 ? "Nobody" : civs[index]?.name ?? `Civ ${index}`;
  const header = <h3>Infrastructure condition · snapshot {at}</h3>;
  if (reading.status !== "ok") {
    const text = reading.status === "disabled" ? "Infrastructure condition is off in this run (--infrastructure-condition not recorded)."
      : reading.status === "absent" ? `No infrastructure record at snapshot ${at}, although the run records it elsewhere: this turn is unknown.`
      : `The infrastructure record at snapshot ${at} is malformed (${reading.reason}); nothing is shown from it.`;
    return <section className="systems-section" aria-label="Infrastructure condition">{header}<p className="systems-note">{text}</p></section>;
  }
  const record = reading.record;
  const receipts = new Map((record.receipts ?? []).map((r) => [r.wid, r]));
  const trace = (aid: number) => (series.get(aid) ?? []).filter((p) => p.turn <= at);
  const thisTurn = (r: InfraReceipt | undefined) => {
    if (reading.frame === "unsettled") return "Unknown (no settled Phase 2)";
    if (!r) return "Not planned";
    const why = r.reasons.map((x) => REASON[x] ?? words(x)).join(", ");
    const shared = r.shared ? ` · shared column, granary asked ${show(r.granary_request)} first` : "";
    return (r.status === "stalled" ? `Stalled: ${why || "unknown"}`
      : `${show(r.delivered)} of ${show(r.requested)} work${why ? ` (limited: ${why})` : ""}`) + shared;
  };
  const stallText = (w: InfraWork) => {
    const parts = Object.entries(w.stalls).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
      .map(([k, v]) => `${REASON[k] ?? words(k)} ${v}`);
    return parts.length ? parts.join(", ") : "None";
  };
  const assetRow = (a: InfraAsset) => <tr key={a.aid}>
    <td>{a.aid}</td><td>{KIND[a.kind]}</td><td>{region(a.region)}</td><td>{civ(a.responsible)}</td>
    <td>{show(a.condition)}</td><td>{show(a.service)}{record.mode === "record_only" && a.status !== "inactive" && a.status !== "destroyed" ? ` (would be ${show(a.condition_service)})` : ""}</td>
    <td>{STATUS[a.status]}{a.cause ? ` (${words(a.cause)}, turn ${a.status_turn})` : a.status === "failed" ? ` since turn ${a.failed_turn}` : ""}</td>
    <td>{a.kind !== "irrigation" ? "—" : a.food_at_risk === null ? "Unobserved" : show(a.food_at_risk)}</td>
    <td><Trace points={trace(a.aid)} /></td>
  </tr>;
  const counters = record.counters;
  const named = record.receipts?.some(r => r.crew_mode !== undefined) ?? false;
  return <section className="systems-section" aria-label="Infrastructure condition">
    {header}
    <p className="systems-note">{named ? `Named farm crews (${record.receipts?.find(r => r.crew_mode)?.crew_mode}): reserved adult farmers give only their available farm time; ordinary income for that work is withheld. Accepted wages go to the named workers and ceiling refusals return to the payer. Materials remain a public-works sink. Paid bills reserve one extra coin for separate rounding; cost-only keeps the same work and spending.` : MODE_NOTE[record.mode]} Serving works wear each turn (irrigation {show(0.01)}, roads {show(0.005)}); service is min(1, condition ÷ 0.5); {named ? "materials leave the economy through the public-works sink" : "the works' coins go to a public-works sink that pays no one and the farmers are unpaid"}; food at risk is the food an irrigation work's region would lose over the budget horizon without repair (the arable ceiling lost × observed production ÷ arable capacity); irrigation's arable bonus scales with service, and irrigation's water effect and a road's two-hop trade range need service of at least 0.5. Constants are declared, not calibrated.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Infrastructure assets at snapshot ${at}`}>
      <thead><tr><th>Id</th><th>Kind</th><th>Region</th><th>Responsible</th><th>Condition</th><th>Service</th><th>Status</th><th>Food at risk</th><th>History</th></tr></thead>
      <tbody>{record.assets.length === 0 && record.terminal.length === 0
        ? <tr><td colSpan={9}>No irrigation work or road is recorded (recorded: none).</td></tr>
        : [...record.assets, ...record.terminal].map(assetRow)}</tbody>
    </table></div>
    {reading.frame === "no_works" ? <p className="systems-note">This mode opens no works: there are no repair receipts to show.</p> : <>
      {reading.frame === "unsettled" ? <p className="systems-note">No Phase 2 was settled in simulation turn {record.source_turn}: this turn's works, receipts and charges are unknown, not zero.</p> : null}
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Infrastructure works at snapshot ${at}`}>
        <thead><tr><th>Work</th><th>Asset</th><th>Cause</th><th>Progress</th><th>This turn</th><th>Stall turns</th><th>Funding</th></tr></thead>
        <tbody>{record.works.length === 0 ? <tr><td colSpan={7}>No open work (recorded: none).</td></tr>
          : record.works.map((w) => <tr key={w.wid}>
            <td>{w.wid}</td><td>{KIND[w.kind]} {w.aid} in {region(w.region)}</td>
            <td>{w.cause === "wear" ? "Wear" : `${words(w.cause)}${w.war_key ? ` (${w.war_key})` : ""}`}, opened turn {w.opened_turn} at {show(w.opened_condition)}</td>
            <td>{show(w.delivered)} of {show(w.scope)} work</td><td>{thisTurn(receipts.get(w.wid))}</td>
            <td>{stallText(w)}</td><td>{coins(w.coin_cost_milli)} coins, {show(w.timber_used)} timber; {civ(w.controller)} pays</td>
          </tr>)}</tbody>
      </table></div>
      {record.ledger && record.ledger.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Works charges at snapshot ${at}`}>
        <thead><tr><th>Civilization</th><th>Work</th><th>Coins (cost)</th><th>Treasury charged</th><th>RS2 charged</th><th>Works envelope</th></tr></thead>
        <tbody>{record.ledger.map((row) => <tr key={row.civ}>
          <td>{civ(row.civ)}</td><td>{show(row.work_delivered)}</td><td>{coins(row.coin_cost_milli)}</td><td>{row.charged}</td>
          <td>{row.rs2_charged}</td><td>{row.envelope === null ? "No budget rule" : row.envelope}</td>
        </tr>)}</tbody>
      </table></div> : null}
    </>}
    {named ? <>
      <h4>Named public-works crews</h4>
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Infrastructure crews at snapshot ${at}`}>
        <thead><tr><th>Work / person</th><th>Region</th><th>Reserved / worked</th><th>Wages accepted / refused</th><th>Ordinary income withheld</th></tr></thead>
        <tbody>{record.receipts?.flatMap(r=>(r.members ?? []).map(m=><tr key={`${r.wid}-${m.agent_id}`}>
          <td>{r.wid} / person {m.agent_id}</td><td>{region(r.region)}</td><td>{show(m.share)} / {show(m.worked)}</td>
          <td>{coins(m.wages_milli)} / {coins(m.wage_refused_milli)}</td><td>{show(m.income_replaced)}</td>
        </tr>))}</tbody>
      </table></div>
    </> : null}
    {record.timber_needs !== undefined ? <>
      <h4>Timber asked of the woodcutters</h4>
      <p className="systems-note">Recorded at this snapshot's Phase 10: the open works' timber for one turn, asked of PL1's woodcutting expeditions only after every RS2 need of the turn (RS2's want in the same region counts first), with the same forests, crews, wages and work reservation.{(record.timber_needs_dropped ?? 0) > 0 ? ` ${record.timber_needs_dropped} more rows were not kept.` : ""}</p>
      {record.timber_needs.length === 0 ? <p className="systems-note">No work asked for timber at this snapshot (recorded: none).</p>
        : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Works timber need at snapshot ${at}`}>
          <thead><tr><th>Region</th><th>Works</th><th>Want</th><th>RS2 want first</th><th>Free + on the way</th><th>Gap</th><th>Woodcutters</th></tr></thead>
          <tbody>{record.timber_needs.map((r) => <tr key={r.region}>
            <td>{region(r.region)}</td><td>{r.works.join(", ")}</td><td>{show(r.want)}</td><td>{show(r.rs2_want)}</td>
            <td>{show(r.free)} + {show(r.in_transit)}</td><td>{show(r.gap)}</td>
            <td>{TIMBER[r.status]}{r.eid !== null ? ` (expedition ${r.eid})` : ""}{r.reason ? `: ${words(r.reason)}` : ""}</td>
          </tr>)}</tbody>
        </table></div>}
    </> : null}
    <h4>Damage</h4>
    {record.damages.length === 0 && (record.skipped_damages ?? []).length === 0 ? <p className="systems-note">No war or flood damage is recorded (recorded: none).</p>
      : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Infrastructure damage to snapshot ${at}`}>
        <thead><tr><th>Turn</th><th>Asset</th><th>Cause</th><th>Condition lost</th></tr></thead>
        <tbody>{[...record.damages].reverse().map((d) => <tr key={d.did}>
          <td>{d.turn}</td><td>{KIND[d.kind]} {d.aid} in {region(d.region)}</td>
          <td>{CAUSE[d.event] ?? words(d.event)}{d.event === "flood" && d.ref ? ` (event ${d.ref})` : d.war_key ? ` (${d.war_key})` : ""}</td>
          <td>{show(d.amount)} ({show(d.condition_before)} → {show(d.condition_after)})</td>
        </tr>)}
        {[...(record.skipped_damages ?? [])].reverse().map((d) => <tr key={`skipped-${d.turn}-${d.aid}-${d.event}`}>
          <td>{d.turn}</td><td>Asset {d.aid} in {region(d.region)}</td>
          <td>{CAUSE[d.event] ?? words(d.event)}{d.ref ? ` (event ${d.ref})` : ""}: skipped, already damaged this turn (damage {d.kept})</td>
          <td>None ({show(d.amount)} not taken)</td>
        </tr>)}</tbody>
      </table></div>}
    <h4>Underfunded public works</h4>
    {story === null ? <p className="systems-note">No work has stalled up to this snapshot (recorded).</p>
      : <p className="systems-note">Directly recorded: work {story.work.wid} on {KIND[story.work.kind].toLowerCase()} {story.work.aid} in {region(story.work.region)} opened at turn {story.work.opened_turn} (condition {show(story.work.opened_condition)}, cause {words(story.work.cause)}); by snapshot {story.seen_turn} it had stalled {story.work.stalled_turns} turn{story.work.stalled_turns === 1 ? "" : "s"} ({story.stalls.map(([k, v]) => `${REASON[k] ?? words(k)} ${v}`).join(", ")}) and delivered {show(story.work.delivered)} of {show(story.work.scope)} work for {coins(story.work.coin_cost_milli)} coins{story.work.status !== "open" ? `; it ended ${words(story.work.status)}${story.work.closed_reason ? ` (${words(story.work.closed_reason)})` : ""} at turn ${story.work.closed_turn}` : ""}.{story.failed_turn !== null ? ` The asset failed (condition 0) at turn ${story.failed_turn}.` : ""}{story.asset ? ` Its condition is ${show(story.asset.condition)} now.` : ""}</p>}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Infrastructure counters to snapshot ${at}`}><tbody>
      <tr><th scope="row">Assets opened / failed / restored</th><td>{show(counters.assets_opened ?? 0)} / {show(counters.assets_failed ?? 0)} / {show(counters.assets_restored ?? 0)}</td></tr>
      <tr><th scope="row">Inactive / destroyed</th><td>{show(counters.assets_inactive ?? 0)} / {show(counters.assets_destroyed ?? 0)}</td></tr>
      <tr><th scope="row">Condition lost to wear / damage</th><td>{show(counters.wear ?? 0)} / {show(counters.damage ?? 0)}</td></tr>
      <tr><th scope="row">Damage events: conquest / sack / flood</th><td>{show(counters.damages_conquest ?? 0)} / {show(counters.damages_sack ?? 0)} / {show(counters.damages_flood ?? 0)}</td></tr>
      {record.works_enabled ? <>
        <tr><th scope="row">Work delivered / credited</th><td>{show(counters.work_delivered ?? 0)} / {show(counters.work_credited ?? 0)}</td></tr>
        <tr><th scope="row">Stalled work-turns by cause</th><td>{["no_timber", "no_coins", "no_labor", "no_envelope", "granary_first"]
          .map((k) => `${REASON[k]} ${show(counters[`stalled_${k}`] ?? 0)}`).join("; ")}</td></tr>
        <tr><th scope="row">Charged to treasuries, paid to no one (public works)</th><td>{coins(record.sink_milli)} coins</td></tr>
      </> : null}
    </tbody></table></div>
  </section>;
}
