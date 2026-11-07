import { useMemo, type ReactNode } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import {
  attributionOn, BURDEN_LABEL, NATURE_LABEL, readAttribution, UNIT_LABEL, type AttributionFrame,
} from "../../lib/attributionRecords";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const CAUSE_LABEL: Record<string, string> = {
  battle: "battle", trapped: "trapped after a lost battle", revolt: "occupation revolt", attrition: "attrition",
  natural: "natural death while enlisted",
};
const IDENTITY_LABEL: Record<string, string> = {
  restored: "restored: a new polity under the dead polity's index and name",
  revived: "alive again under the same index, without a new founding",
  name_reused: "a new index named like an older polity", renamed: "renamed under the same index",
};

/** The completed turn's attribution records only; never reads final-world state. */
export function AttributionRecords({ bundle, snapshot, currentTurn }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const on = useMemo(() => attributionOn(bundle.history), [bundle]);
  const reading = readAttribution(snapshot, on, regions.length, civs.length);
  const at = snapshot?.turn ?? currentTurn;
  const heading = <h3>Attribution records{reading.state !== "disabled" && reading.state !== "absent"
    && reading.state !== "malformed" ? ` · snapshot ${reading.record.source_turn + 1}` : ""}</h3>;
  const section = (body: ReactNode) =>
    <section className="systems-section" aria-label="Attribution records">{heading}{body}</section>;
  if (reading.state === "disabled") {
    return section(<p className="systems-note">Attribution records are off in this run (--attribution-records not recorded).</p>);
  }
  if (reading.state === "absent") {
    return section(<p className="systems-note">No attribution record at snapshot {at}: unknown, not zero.</p>);
  }
  if (reading.state === "malformed") {
    return section(<p className="systems-note">The attribution record at snapshot {at} was rejected as malformed: {reading.reason}. Nothing is shown from it.</p>);
  }
  const source = reading.record.source_turn;
  if (reading.state === "unobserved") {
    return section(<p className="systems-note">Simulation turn {source} was not observed: who did what to whom that turn is unknown, not zero.</p>);
  }
  const intro = <p className="systems-note">Simulation turn {source}. Observation-only records of actor, victim and cause, taken at the event; nothing in the simulation reads them. Civilizations are named as they were at the event.</p>;
  if (reading.state === "recorded_zero") {
    const g = reading.frame.granary;
    return section(<>{intro}<p className="systems-note">Nothing was attributed this turn: no enlisted soldier died, no burden was recorded, no granary grain was seized{g.active ? "" : " (granaries are off: seizures unknown, not zero)"} and no civilization index was reused (recorded zero).</p></>);
  }
  return section(<>{intro}<Frame frame={reading.frame} source={source} regionName={(i) => regions[i]?.name ?? `Region ${i}`} /></>);
}

function Frame({ frame, source, regionName }: { frame: AttributionFrame; source: number; regionName: (i: number) => string }) {
  const c = frame.casualties;
  const failed = c.armies.filter((a) => a.closes === false);
  const unchecked = c.armies.filter((a) => a.closes === null).length;
  const name = (n: string | null, i: number | null) => n ?? (i === null ? "no one" : `Civ ${i}`);
  return <>
    {c.rows.length === 0 ? <p className="systems-note">No enlisted soldier died this turn (recorded zero).</p> : <>
      <p className="systems-note">Soldiers' deaths: combat {c.by_class.combat ?? 0}, attrition {c.by_class.attrition ?? 0}, natural {c.by_class.natural ?? 0}. Army casualty counters merge natural deaths; this record keeps them apart{failed.length ? "" : unchecked ? `; ${unchecked} army closure(s) unchecked (no baseline)` : "; every army's counter closes"}.{c.unresolved ? ` ${c.unresolved} combat death(s) could not be matched to a battle record.` : ""}</p>
      {failed.length ? <p className="systems-note">Army closures failed: {failed.map((a) => `${a.army} (recorded ${a.recorded}, counter ${show(a.counter_change, 0)})`).join(", ")}.</p> : null}
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Soldiers' deaths at snapshot ${source + 1}`}>
        <thead><tr><th>War</th><th>Died (victim)</th><th>Killed by (actor)</th><th>Cause</th><th>Deaths</th></tr></thead>
        <tbody>{c.rows.map((r, i) => <tr key={i}>
          <td>{r.war ?? "Unknown"}{r.war_start !== null ? ` (from turn ${r.war_start})` : ""}</td>
          <td>{name(r.victim_name, r.victim)}</td>
          <td>{r.actor === null && r.actor_name === null ? `no actor${r.opponent_name ? ` (at war with ${r.opponent_name})` : ""}` : name(r.actor_name, r.actor)}</td>
          <td>{CAUSE_LABEL[r.cause] ?? r.cause}{r.kind ? ` (${r.kind})` : ""}</td>
          <td>{r.deaths}</td>
        </tr>)}</tbody>
      </table></div>
    </>}
    {!frame.granary.active ? <p className="systems-note">Granaries are off: seizures are not observed (unknown, not zero).</p>
      : frame.granary.seizures.length === 0 ? <p className="systems-note">No granary grain was seized this turn (recorded zero){frame.granary.unattributed ? `; ${frame.granary.unattributed} seizure(s) were not attributed` : ""}.</p> : <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Granary seizures at snapshot ${source + 1}`}>
          <thead><tr><th>Region</th><th>Cause</th><th>Seized by</th><th>From</th><th>Grain</th></tr></thead>
          <tbody>{frame.granary.seizures.map((s) => <tr key={s.flow}>
            <td>{regionName(s.region)}</td><td>{s.cause}{s.via && s.via !== "war" ? ` (${s.via})` : ""}</td>
            <td>{name(s.actor_name, s.actor)}</td>
            <td>{name(s.victim_name, s.victim)}{s.owner_stale ? ` (the granary books still name ${name(s.books_owner_name, s.books_owner)})` : ""}</td>
            <td>{show(s.grain)}</td>
          </tr>)}</tbody>
        </table></div>
        {frame.granary.unattributed ? <p className="systems-note">{frame.granary.unattributed} seizure(s) of this turn were not attributed.</p> : null}
      </>}
    {frame.burdens.pairs.length === 0 ? <p className="systems-note">No burden between polities was recorded this turn (recorded zero).</p> : <>
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Burdens at snapshot ${source + 1}`}>
        <thead><tr><th>Burden</th><th>By (actor)</th><th>On (victim)</th><th>Nature</th><th>Amount</th><th>Events</th></tr></thead>
        <tbody>{frame.burdens.pairs.map((p, i) => <tr key={i} title={p.authority}>
          <td>{BURDEN_LABEL[p.kind] ?? p.kind}{p.internal ? " (own realm)" : ""}</td>
          <td>{name(p.actor_name, p.actor)}</td><td>{name(p.victim_name, p.victim)}</td>
          <td>{NATURE_LABEL[p.nature]}</td>
          <td>{show(p.amount)} {UNIT_LABEL[p.unit]}{p.unknown ? ` (+${p.unknown} unknown)` : ""}</td>
          <td>{p.events}</td>
        </tr>)}</tbody>
      </table></div>
      {frame.burdens.entries_dropped ? <p className="systems-note">{frame.burdens.entries_dropped} detailed entries were not kept; the pairs above include them.</p> : null}
    </>}
    {frame.identity.length ? <ul className="systems-list" aria-label={`Identity events at snapshot ${source + 1}`}>
      {frame.identity.map((e, i) => <li key={i}>{e.name} (index {e.civ}): {IDENTITY_LABEL[e.kind] ?? e.kind}. Records under this index or name before turn {e.turn} belong to the earlier polity.</li>)}
    </ul> : null}
  </>;
}
