import type { Bundle, TurnSnapshot } from "../../types";
import {
  NO_OPENING, unmetByReason, veteranFunnel, veteranOutcomeCounts, veteransAt,
  type VeteranOutcomeRecord, type VeteranRecord,
} from "../../lib/veterans";

const show = (value: number | null | undefined) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ").replace("placed:", "placed as ");
const MODE_NOTE: Record<string, string> = {
  priority: "Priority mode: eligible veterans are put first, among people who are otherwise eligible, for workshop crews and (when those packages run) apprenticeship seats and repair crews.",
  record_only: "Record-only control: veterans are captured and followed the same way, and the panel shows who would have been put first, but nobody's order changes.",
};
const STATUS: Record<string, string> = {
  waiting: "Waiting (eligible, not placed)", placed: "Placed this turn", ineligible: "Not eligible", closed: "Closed",
};

function outcome(o: VeteranOutcomeRecord, region: (index: number) => string): string {
  const d = o.detail ?? {};
  if (o.kind === "migrated" && typeof d.from === "number" && typeof d.to === "number") {
    return `turn ${o.turn}: moved from ${region(d.from)} to ${region(d.to)}`;
  }
  if (o.kind.startsWith("placed:")) return `turn ${o.turn}: ${words(o.kind)}${d.site !== null && d.site !== undefined ? ` (site ${d.site})` : ""}${d.prioritised ? ", put first" : ""}`;
  return `turn ${o.turn}: ${words(o.kind)}`;
}

/** Completed-turn veterans only; never reads final-world state. */
export function Veterans({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const record = veteransAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Veterans">
    <h3>Veterans</h3><p className="systems-note">Veteran reintegration is not observed or is unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const civ = (index: number) => (index < 0 ? "Unknown" : civs[index]?.name ?? `Civ ${index}`);
  const war = (v: { war_key: string | null; war_start: number | null }) =>
    v.war_key === null ? "No war record" : `${v.war_key.replace(":", " – ")} (from turn ${v.war_start})`;
  const unmet = unmetByReason(record);
  const frame = record.frame;
  const noOpening = unmet === null ? null : NO_OPENING.reduce((n, k) => n + (unmet.get(k)?.length ?? 0), 0);
  const regionButton = (index: number) => <button type="button" className="systems-link" onClick={() => onSelectRegion(region(index))}>{region(index)}</button>;
  const row = (v: VeteranRecord) => <tr key={v.record_id}>
    <td>{v.agent_id}</td>
    <td>{civ(v.civ)} · {v.army_id}</td>
    <td>{war(v)}</td>
    <td>{words(v.cause)}</td>
    <td>turn {v.released_turn}</td>
    <td>{regionButton(v.region)}</td>
    <td>{STATUS[v.status]}{v.reason ? ` (${words(v.reason)})` : ""}{v.closed_reason ? `: ${words(v.closed_reason)}` : ""}</td>
    <td>{v.placements} ({v.placed_turns} turns)</td>
    <td>{v.outcomes_dropped ? `${v.outcomes_dropped} earlier not kept; ` : ""}{v.outcomes.map((o) => outcome(o, region)).join("; ")}</td>
  </tr>;
  return <section className="systems-section" aria-label="Veterans">
    <h3>Veterans · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Veterans are named people who left a real army alive: deserters, survivors of a broken army and soldiers sent home. They stay eligible for {show(Number(record.parameters.eligible_turns))} turns while adult, off every roster and living in land ruled by the civilization they served. Nothing is guaranteed: with no opening there is no placement, and no person, money or skill is created.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Veteran funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{veteranFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}</tbody>
    </table></div>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Veteran outcomes at snapshot ${turn}`}>
      <thead><tr><th>Outcome (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{veteranOutcomeCounts(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}</tbody>
    </table></div>
    {frame === null ? <p className="systems-note">No veteran turn was recorded in simulation turn {record.source_turn}; releases, placements and waiting are unknown, not zero.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Veterans this turn at snapshot ${turn}`}>
        <thead><tr><th>This turn</th><th>People</th></tr></thead>
        <tbody>
          <tr><td>Released alive</td><td>{frame.captured_total}{frame.captured_total ? ` (${Object.entries(frame.captured_by_cause).map(([k, n]) => `${n} ${words(k)}`).join(", ")})` : ""}</td></tr>
          <tr><td>{record.mode === "priority" ? "Put first for crews" : "Would have been put first"}</td><td>{frame.offered === null ? "Unknown" : frame.offered.map(([r, ids]) => `${region(r)}: ${ids.join(", ") || "none"}`).join("; ") || "No workshop site"}</td></tr>
          <tr><td>Placed</td><td>{frame.placed.length ? frame.placed.map((p) => `${p.agent_id} ${words(p.kind)} in ${region(p.region)}${p.prioritised ? " (put first)" : ""}`).join("; ") : "Nobody"}</td></tr>
          <tr><td>Waiting with no opening</td><td>{noOpening === null ? "Unknown" : `${noOpening} (${NO_OPENING.map((k) => `${unmet?.get(k)?.length ?? 0} ${words(k)}`).join(", ")})`}</td></tr>
          <tr><td>Waiting, an opening existed</td><td>{unmet === null ? "Unknown" : [...unmet].filter(([k]) => !NO_OPENING.includes(k)).map(([k, ids]) => `${ids.length} ${words(k)}`).join(", ") || "0"}</td></tr>
        </tbody>
      </table></div>}
    {record.veterans.length === 0 ? <p className="systems-note">No veteran record is open.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open veteran records at snapshot ${turn}`}>
        <thead><tr><th>Person</th><th>Served</th><th>War</th><th>Left by</th><th>Released</th><th>Lives in</th><th>Status</th><th>Placements</th><th>Dated outcomes</th></tr></thead>
        <tbody>{record.veterans.map(row)}</tbody>
      </table></div>}
    {record.veterans_omitted ? <p className="systems-note">{record.veterans_omitted} more open records are not shown in this snapshot.</p> : null}
    {record.closed.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Veteran records closed at snapshot ${turn}`}>
        <thead><tr><th>Person</th><th>Served</th><th>War</th><th>Left by</th><th>Released</th><th>Lived in</th><th>Status</th><th>Placements</th><th>Dated outcomes</th></tr></thead>
        <tbody>{record.closed.map(row)}</tbody>
      </table></div> : null}
  </section>;
}
