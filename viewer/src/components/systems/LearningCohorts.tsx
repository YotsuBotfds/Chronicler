import type { Bundle, TurnSnapshot } from "../../types";
import { learningCohortsAt, learningFunnel, OCCUPATIONS } from "../../lib/learningCohorts";

const show = (value: number | null | undefined) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const trade = (code: number) => OCCUPATIONS[code] ?? `Occupation ${code}`;
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const MODE_NOTE: Record<string, string> = {
  learn: "Learn mode: a member who completes the course gains skill in the trade they practised when enrolling; the civ capacity, purpose and promotion rules that already read skill then read it.",
  no_learning: "No-learning control: cohorts attend, give up the same income and occupy the same paid teaching, and completions are recorded, but nobody's skill changes.",
};

/** Completed-turn academy cohorts only; never reads final-world state. */
export function LearningCohorts({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const record = learningCohortsAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Academy learners">
    <h3>Academy learners</h3><p className="systems-note">Learning cohorts are not observed or are unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const receipts = new Map((record.receipts ?? []).map((r) => [r.cohort_id, r]));
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  return <section className="systems-section" aria-label="Academy learners">
    <h3>Academy learners · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Members are named adults living in the academy's region. They attend only when the academy's Scholars actually deliver paid teaching that turn, and attending withholds part of their ordinary income. A school that exists or pays upkeep does not by itself mean anyone learned.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Learning funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{learningFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}
        <tr><td>Income withheld for attendance</td><td>{show(record.counters.attendance_income_charged ?? 0)}</td></tr>
      </tbody>
    </table></div>
    {record.cohorts.length === 0 ? <p className="systems-note">No cohort is open.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open cohorts at snapshot ${turn}`}>
        <thead><tr><th>Cohort</th><th>Academy</th><th>Region</th><th>Members</th><th>Sessions</th><th>This turn</th><th>Income withheld</th><th>Why no session</th></tr></thead>
        <tbody>{record.cohorts.map((c) => {
          const r = receipts.get(c.cohort_id);
          const active = c.members.filter((m) => m.status === "active");
          return <tr key={c.cohort_id}>
            <td>#{c.cohort_id} (formed turn {c.formed_turn})</td>
            <td>{c.seat_name}</td>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(region(c.region))}>{region(c.region)}</button></td>
            <td>{active.length} active of {c.members.length} · {active.map((m) => `${m.agent_id} ${trade(m.occupation)} ${m.attended}`).join(", ") || "none"}</td>
            <td>{c.sessions}</td>
            <td>{r ? `${r.attended.length} attended, ${r.no_seat.length} without a seat, ${Object.values(r.unavailable).reduce((a, b) => a + b, 0)} unavailable` : "Unknown"}</td>
            <td>{r ? show(r.income_charged) : "Unknown"}</td>
            <td>{r ? (r.session ? "—" : words(r.no_session_reason)) : "Unknown"}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    {record.receipts === null ? <p className="systems-note">No cohort turn was recorded in simulation turn {record.source_turn}; attendance is unknown, not zero.</p> : null}
    {record.graduates.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Recent graduates at snapshot ${turn}`}>
        <thead><tr><th>Person</th><th>Trade learned</th><th>Completed</th><th>Skill before → after</th></tr></thead>
        <tbody>{record.graduates.slice(-8).map((g) => <tr key={`${g.cohort_id}-${g.agent_id}`}>
          <td>{g.agent_id}</td><td>{trade(g.occupation)}</td><td>turn {g.completed_turn}</td>
          <td>{show(g.skill_before)} → {show(g.skill_after)}{g.granted ? "" : " (no change)"}</td>
        </tr>)}</tbody>
      </table></div> : null}
    {record.archive.length > 0 ? <p className="systems-note">Closed cohorts: {record.archive.map((c) =>
      `#${c.cohort_id} ${c.seat_name} (turn ${c.closed_turn}, ${words(c.closed_reason)}: ${c.completed} completed, ${c.exited} left)`).join("; ")}.</p> : null}
  </section>;
}
