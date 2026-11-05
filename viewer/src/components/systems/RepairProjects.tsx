import type { Bundle, TurnSnapshot } from "../../types";
import {
  progress, repairFunnel, repairProjectsAt, type RepairProjectRecord, type RepairReceiptRecord,
} from "../../lib/repairProjects";

const show = (value: number | null | undefined) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const coins = (milli: number) => (milli / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const MODE_NOTE: Record<string, string> = {
  repair: "Repair mode: work delivered by a project restores its asset's condition pro rata to the deficit it was opened for.",
  cost_only: "Cost-only control: projects reserve the same crews, pay the same wages and coins and use the same timber, but condition never changes.",
};
const REASON: Record<string, string> = {
  no_timber: "no free timber", no_coins: "treasury short", no_labor: "not enough labour",
  no_envelope: "no repairs envelope", unqualified: "no qualified repairer (reduced rate)",
};

/** Completed-turn repair projects only; never reads final-world state. */
export function RepairProjects({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const record = repairProjectsAt(snapshot, regions.length, civs.length);
  if (!record) return <section className="systems-section" aria-label="Repair projects">
    <h3>Repair projects</h3><p className="systems-note">Repair projects are not observed or are unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const civ = (index: number) => civs[index]?.name ?? `Civ ${index}`;
  const receipts = new Map((record.receipts ?? []).map((r) => [r.pid, r]));
  const place = (p: { kind: string; asset: number; region: number }) =>
    <>{p.kind === "granary" ? "Granary in " : `Workshop site ${p.asset} in `}
      <button type="button" className="systems-link" onClick={() => onSelectRegion(region(p.region))}>{region(p.region)}</button></>;
  const cause = (p: RepairProjectRecord) => p.cause === "wear" ? "Wear" :
    `War${p.war_key ? ` (${p.war_key}, began turn ${p.war_start_turn})` : " (war unknown)"}`;
  const thisTurn = (r: RepairReceiptRecord | undefined) => {
    if (!r) return "Unknown";
    const why = r.reasons.map((x) => REASON[x] ?? words(x)).join(", ");
    return r.status === "stalled" ? `Stalled: ${why || "unknown"}` :
      `${show(r.delivered)} work of ${show(r.requested)} planned${why ? ` (limited: ${why})` : ""}`;
  };
  const crew = (r: RepairReceiptRecord | undefined) => {
    if (!r) return "Unknown";
    if (r.kind === "granary") return "Farm labour (anonymous)";
    if (r.crew.length === 0) return "Nobody";
    const tags = (id: number) => [r.qualified.includes(id) ? "qualified" : "", r.veterans.includes(id) ? "veteran" : ""]
      .filter(Boolean).join(", ");
    return r.crew.map((id) => tags(id) ? `${id} (${tags(id)})` : `${id}`).join(", ")
      + ` · share ${show(r.share)}, rate ${show(r.rate)}`;
  };
  const funding = (r: RepairReceiptRecord | undefined) => {
    if (!r) return "Unknown";
    const parts = [];
    if (r.wages_due_milli) parts.push(`wages ${coins(r.wages_milli)}${r.wage_residual_milli ? ` (+${coins(r.wage_residual_milli)} refused by the ceiling)` : ""}`);
    if (r.coin_cost_milli) parts.push(`coins ${coins(r.coin_cost_milli)}`);
    parts.push(`timber ${show(r.timber_used)}`);
    if (r.envelope !== null) parts.push(`envelope ${r.envelope}`);
    if (r.income_replaced !== null) parts.push(`income withheld ${show(r.income_replaced)}`);
    return `${civ(r.payer)}: ${parts.join(", ")}`;
  };
  return <section className="systems-section" aria-label="Repair projects">
    <h3>Repair projects · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Workshop sites and public granaries only. A project opens when an asset's condition falls below {show(record.parameters.open_below)} or after recorded war damage, and is sized to the actual deficit. Workshop repairs are done by named residents reserved for the turn and paid a wage that replaces part of their income; granary repairs use farm labour, timber and coins. Opening a project does not by itself repair anything.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Repair funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{repairFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}
        <tr><td>Work delivered</td><td>{show(record.counters.work_delivered ?? 0)}</td></tr>
        <tr><td>Coins charged</td><td>{show(record.counters.charged ?? 0)}</td></tr>
      </tbody>
    </table></div>
    {record.receipts === null ? <p className="systems-note">No repair work was planned in simulation turn {record.source_turn}; this turn's work, crews and spending are unknown, not zero.</p> : null}
    {record.projects.length === 0 ? <p className="systems-note">No project is open.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open repair projects at snapshot ${turn}`}>
        <thead><tr><th>Project</th><th>Asset</th><th>Cause</th><th>Scope and progress</th><th>This turn</th><th>Crew</th><th>Funding</th><th>Stalls</th></tr></thead>
        <tbody>{record.projects.map((p) => {
          const r = receipts.get(p.pid);
          return <tr key={p.pid}>
            <td>#{p.pid} (opened turn {p.opened_turn} at {show(p.opened_condition)})</td>
            <td>{place(p)}</td>
            <td>{cause(p)}</td>
            <td>{`${show(p.delivered)} of ${show(p.scope)} work (${Math.round(progress(p) * 100)}%)`}{r ? ` · condition ${show(r.condition_before)} → ${show(r.condition_after)}` : ""}</td>
            <td>{record.receipts === null ? "Unknown" : thisTurn(r)}</td>
            <td>{record.receipts === null ? "Unknown" : crew(r)}</td>
            <td>{record.receipts === null ? "Unknown" : funding(r)}</td>
            <td>{Object.keys(p.stalls).length === 0 ? "None" : Object.entries(p.stalls).map(([k, v]) => `${REASON[k] ?? words(k)} ${v}`).join("; ")}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    {record.ledger && record.ledger.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Repair accounts at snapshot ${turn}`}>
        <thead><tr><th>Ruler</th><th>Projects</th><th>Work</th><th>Timber</th><th>Wages</th><th>Coins for work</th><th>Charged (whole units, prepaid remainder)</th></tr></thead>
        <tbody>{record.ledger.map((l) => <tr key={l.civ}>
          <td>{civ(l.civ)}</td><td>{l.projects}</td><td>{show(l.work_delivered)}</td><td>{show(l.timber_used)}</td>
          <td>{coins(l.wages_applied_milli)}</td><td>{coins(l.coin_cost_milli)}</td>
          <td>{`${l.charged} (prepaid ${coins(l.prepaid_before_milli)} → ${coins(l.prepaid_after_milli)})${l.envelope !== null ? ` of envelope ${l.envelope}` : ""}`}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.unmet === null ? null : record.unmet.length === 0 ? null :
      <p className="systems-note">Unmet needs: {record.unmet.map((u) =>
        `${u.kind === "granary" ? "granary" : `workshop site ${u.asset}`} in ${region(u.region)} at ${show(u.condition)} (${words(u.reason)})`).join("; ")}.</p>}
    {record.damages.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Recent war damage at snapshot ${turn}`}>
        <thead><tr><th>Turn</th><th>Asset</th><th>Event</th><th>War</th><th>Condition</th><th>Project</th></tr></thead>
        <tbody>{record.damages.slice(-8).map((d) => <tr key={d.did}>
          <td>{d.turn}</td><td>{place(d)}</td><td>{words(d.event)}</td>
          <td>{d.war_key ? `${d.war_key} (began turn ${d.war_start_turn})` : "Unknown"}</td>
          <td>{`${show(d.condition_before)} → ${show(d.condition_after)}`}</td>
          <td>{d.project === null ? "None yet" : `#${d.project}`}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.closed.length > 0 ? <p className="systems-note">Closed projects: {record.closed.slice(-8).map((p) =>
      `#${p.pid} ${p.kind} in ${region(p.region)} (${p.status === "completed" ? "completed" : `abandoned, ${words(p.closed_reason)}`} turn ${p.closed_turn}: ${show(p.delivered)} of ${show(p.scope)} work)`).join("; ")}.</p> : null}
  </section>;
}
