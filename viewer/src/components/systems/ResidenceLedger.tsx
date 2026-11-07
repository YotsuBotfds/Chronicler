import type { ReactNode } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import { readResidenceLedger } from "../../lib/recordReading";
import { percent, type ResidenceFrame, type ResidenceRegionRow, type SpellEvent } from "../../lib/residenceLedger";

const CLOSURE_LABEL: Record<string, string> = {
  returned: "returned home", resettled: "resettled (settled long enough that home moved to where they live)", died: "died while displaced",
  pool_reset: "closed: the agent pool was rebuilt", unobserved_gap: "closed: turns not observed",
};
/** How many recent snapshots the run summary lists. */
const RECENT = 8;

/**
 * The residence ledger (X1, the displacement contract): where people live, where they
 * belong and why they left, for the completed turn of this snapshot only. Never reads
 * final-world state; a person-level row is not shown (the record keeps aggregates and
 * the turn's spell events by stable id).
 */
export function ResidenceLedger({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const reading = readResidenceLedger(bundle, snapshot, currentTurn);
  const heading = (turn?: number) => <h3>Residence and displacement{turn !== undefined ? ` · snapshot ${turn}` : ""}</h3>;
  const section = (turn: number | undefined, body: ReactNode) =>
    <section className="systems-section" aria-label="Residence and displacement">{heading(turn)}{body}</section>;
  if (reading.record === null) return section(undefined, <p className="systems-note">{reading.note}</p>);
  const record = reading.record;
  const turn = record.source_turn + 1;
  const name = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const link = (index: number) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(name(index))}>{name(index)}</button>;
  const recent = <RecentTurns bundle={bundle} at={snapshot?.turn ?? currentTurn} />;
  if (reading.state === "unobserved" || record.frame === null) {
    return section(turn, <><p className="systems-note">{reading.note} Who lived where and who left in simulation turn {record.source_turn} is unknown, not zero.</p>{recent}</>);
  }
  const frame = record.frame;
  const p = record.parameters as Record<string, number>;
  const intro = <>
    <p className="systems-note">Simulation turn {record.source_turn}, observed since turn {frame.observed_from} (earlier history is unknown, not zero). These are motive-classified ledger spells, not a census of all physical displacement or measured housing pressure. A spell opens for a recorded flight or hunger driver until return, resettlement ({p.rehome_turns ?? 20} turns at one residence; moving on keeps the spell open), death or an observation gap. Its home anchor is a recorded event in the preceding {p.anchor_turns ?? 5} turns: war, famine, persecution, or none. Other or unknown move reasons do not establish a voluntary choice or absence of displacement; the ledger may update home immediately for those moves. Enlistment never changes residence or home.</p>
    <ArrivalSummary frame={frame} turn={turn} link={link} />
  </>;
  if (reading.state === "recorded_zero") {
    return section(turn, <>{intro}<p className="systems-note">{reading.note}.</p>{recent}</>);
  }
  return section(turn, <>{intro}<Frame frame={frame} events={record.events ?? []} dropped={record.events_dropped}
    turn={turn} link={link} />{recent}</>);
}

function Frame({ frame, events, dropped, turn, link }: {
  frame: ResidenceFrame; events: SpellEvent[]; dropped: number; turn: number; link: (index: number) => ReactNode;
}) {
  const t = frame.totals;
  const rows = [...frame.regions].sort((a, b) => a.region - b.region);
  const stock = rows.filter((r) => r.residents || r.displaced || r.displaced_from);
  const flows = rows.filter((r) => r.departures || r.arrivals || r.opened || r.returned || r.resettled || r.died_displaced || r.deaths);
  const away = rows.filter((r) => r.attached || r.in_transit);
  const closed = (["returned", "resettled", "died", "pool_reset", "unobserved_gap"] as const).filter((k) => t[k] > 0);
  const longest = events.filter((e) => e.kind !== "opened").reduce((m, e) => Math.max(m, e.length), 0);
  return <>
    <p className="systems-note">{t.displaced} of {t.observed} people observed have motive-classified displacement spells ({percent(t.displaced, t.observed)}): {t.displaced_flight} recorded flight, {t.displaced_hunger} recorded hunger. Anchored at home to war {t.displaced_war}, famine {t.displaced_famine}, persecution {t.displaced_persecution}, no event {t.displaced_none}{t.anchor_partial ? ` (${t.anchor_partial} of them left before the ledger had watched their home for the whole window)` : ""}.{t.deferred ? ` ${t.deferred} merchant(s) first seen on a trip are recorded when it ends.` : ""}</p>
    <p className="systems-note">This turn: {t.moves} moves ({t.moves_flight} flight, {t.moves_hunger} hunger, {t.moves_voluntary} voluntary, {t.moves_other} other); {t.opened} spell(s) opened{t.opened_war ? ` (${t.opened_war} anchored to war)` : ""}; {closed.length ? closed.map((k) => `${t[k]} ${CLOSURE_LABEL[k]}`).join(", ") : "no spell closed"}; {t.rehomed} migrant(s) took a new home; {t.deaths} death(s){longest ? `; the longest spell closed lasted ${longest} turns` : ""}.{t.trip_relocations ? ` ${t.trip_relocations} trip(s) ended away from home (an unclassified relocation).` : ""}</p>
    {stock.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open displacement spells at snapshot ${turn}`}>
      <thead><tr><th>Region</th><th>Residents</th><th>Displaced here (fled · hungry)</th><th>Anchor: war · famine · persecution · none</th><th>Displaced from here (war-anchored)</th></tr></thead>
      <tbody>{stock.map((r) => <tr key={r.region}>
        <td>{link(r.region)}</td><td>{r.residents}</td>
        <td>{r.displaced} ({r.displaced_flight} · {r.displaced_hunger})</td>
        <td>{r.displaced_war} · {r.displaced_famine} · {r.displaced_persecution} · {r.displaced_none}</td>
        <td>{r.displaced_from} ({r.displaced_from_war})</td>
      </tr>)}</tbody>
    </table></div> : <p className="systems-note">No one is recorded in any region (recorded zero).</p>}
    {flows.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Movement and spells at snapshot ${turn}`}>
      <thead><tr><th>Region</th><th>Departures (flight · hunger · voluntary · other)</th><th>Arrivals (displaced)</th><th>Spells opened (war-anchored)</th><th>Returned home (war-anchored)</th><th>Resettled</th><th>Died displaced</th><th>Deaths</th></tr></thead>
      <tbody>{flows.map((r: ResidenceRegionRow) => <tr key={r.region}>
        <td>{link(r.region)}</td>
        <td>{r.departures} ({r.departures_flight} · {r.departures_hunger} · {r.departures_voluntary} · {r.departures_other})</td>
        <td>{r.arrivals} ({r.arrivals_displaced})</td><td>{r.opened} ({r.opened_war})</td><td>{r.returned} ({r.returned_war})</td>
        <td>{r.resettled}</td><td>{r.died_displaced}</td><td>{r.deaths}</td>
      </tr>)}</tbody>
    </table></div> : <p className="systems-note">No one moved, left, returned, resettled or died this turn (recorded zero).</p>}
    {away.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Away from home at snapshot ${turn}`}>
      <thead><tr><th>Home region</th><th>On an army roster</th><th>With the army elsewhere</th><th>Merchants in transit</th></tr></thead>
      <tbody>{away.map((r) => <tr key={r.region}>
        <td>{link(r.region)}</td><td>{r.attached}</td><td>{r.attached_away}</td><td>{r.in_transit}</td>
      </tr>)}</tbody>
    </table></div> : <p className="systems-note">No one is on an army roster or travelling (recorded zero).</p>}
    {dropped ? <p className="systems-note">{dropped} spell event(s) of this turn are counted above but not kept by person.</p> : null}
    <p className="systems-note">For comparison only (the measures this record replaces): {percent(t.recent_movers_native, t.alive)} moved in the last five turns (the native displacement counter) and {percent(t.away_from_birth_region, t.alive)} live outside their birth region.</p>
  </>;
}

function ArrivalSummary({ frame, turn, link }: {
  frame: ResidenceFrame; turn: number; link: (index: number) => ReactNode;
}) {
  const diagnostic = frame.arrival_diagnostics;
  if (!diagnostic) return <p className="systems-note">Recent residence-arrival diagnostics were not recorded in this older observation; unknown, not zero.</p>;
  const rows = frame.regions.filter(r => Number(r.recent_residence_arrivals) > 0);
  return <div>
    <h4>Recent residence arrivals</h4>
    <p className="systems-note">{frame.totals.recent_residence_arrivals} retained living residents have a recorded residence arrival within {diagnostic.window_turns} turns; {frame.totals.recent_residence_arrivals_unknown_reason} have an unclassified latest arrival reason. Each person is counted once at their current recorded residence; returns and trips ending elsewhere can count. Arrival does not establish forced displacement or measured crowding. {diagnostic.complete ? "The observation window and population coverage are complete." : `Coverage ${diagnostic.coverage_complete ? "complete" : "incomplete"}; window ${diagnostic.window_complete ? "complete" : "incomplete"}. These are partial observed counts; the population arrival share is unknown, not zero.`}</p>
    {rows.length ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Recent residence arrivals at snapshot ${turn}`}>
      <thead><tr><th>Current residence</th><th>Observed residents</th><th>Recent arrivals</th><th>Latest reason unknown</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.region}><td>{link(r.region)}</td><td>{r.residents}</td><td>{r.recent_residence_arrivals}</td><td>{r.recent_residence_arrivals_unknown_reason}</td></tr>)}</tbody>
    </table></div> : <p className="systems-note">{diagnostic.complete ? "No recent residence arrivals (recorded zero)." : "No retained recent-arrival observations; incomplete coverage cannot establish a population zero."}</p>}
  </div>;
}

/** The last few snapshots up to this one, each read on its own (its state named when it has no frame). */
function RecentTurns({ bundle, at }: { bundle: Bundle; at: number }) {
  const history = Array.isArray(bundle.history) ? bundle.history : [];
  const shown = history.filter((s) => s !== null && typeof s.turn === "number" && s.turn <= at).slice(-RECENT);
  if (shown.length < 2) return null;
  return <div className="systems-table-wrap"><table className="systems-table" aria-label={`Residence ledger, recent snapshots to ${at}`}>
    <thead><tr><th>Snapshot</th><th>Displaced</th><th>Opened</th><th>Returned</th><th>Resettled</th><th>Died displaced</th><th>Moves</th></tr></thead>
    <tbody>{shown.map((s) => {
      const r = readResidenceLedger(bundle, s, s.turn);
      const f = r.record?.frame ?? null;
      if (f === null) return <tr key={s.turn}><td>{s.turn}</td><td colSpan={6}>{r.state === "unobserved" ? "not observed (unknown)"
        : r.state === "malformed" ? "malformed record (not shown)" : "no record (unknown)"}</td></tr>;
      const t = f.totals;
      return <tr key={s.turn}><td>{s.turn}</td><td>{t.displaced}</td><td>{t.opened}</td><td>{t.returned}</td>
        <td>{t.resettled}</td><td>{t.died}</td><td>{t.moves}</td></tr>;
    })}</tbody>
  </table></div>;
}
