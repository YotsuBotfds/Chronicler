import type { Bundle, TurnSnapshot } from "../../types";
import {
  apprenticeshipFunnel, apprenticeshipOutcomes, readApprenticeship, type ApprenticeshipSiteReceipt, type SeatRecord,
} from "../../lib/apprenticeship";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const people = (list: number[]) => (list.length ? list.join(", ") : "none");
const MODE_NOTE: Record<string, string> = {
  train: "Train mode: an apprentice who attends the required turns earns a workshop qualification, kept for life wherever they live.",
  no_qualification: "No-qualification control: apprentices attend, give up the same income and their mentors spend the same time, and completions are recorded, but completing grants no qualification. Service qualifications accrue as in train mode.",
};

function seatText(s: SeatRecord): string {
  const tag = `${s.agent_id}${s.veteran ? " (veteran)" : ""}${s.new ? " new" : ""}`;
  if (s.outcome === "attended") {
    const done = s.ending ? `, ${words(s.ending)}` : "";
    return `${tag}: taught by ${s.mentor}, income given up ${show(s.income_forgone)}${done}`;
  }
  if (s.outcome === "missed") return `${tag}: missed (${words(s.reason)})${s.ending ? `, ${words(s.ending)}` : ""}`;
  return `${tag}: ended (${words(s.reason)})`;
}

function stipendText(r: ApprenticeshipSiteReceipt): string {
  const attended = r.seats.filter((s) => s.outcome === "attended");
  if (!attended.length) return "—";
  const due = attended.reduce((a, s) => a + s.stipend_due, 0);
  const paid = attended.reduce((a, s) => a + s.stipend_paid, 0);
  if (r.stipend_status === null) return "Unknown";
  return `${show(paid / 1000)} of ${show(due / 1000)} (${words(r.stipend_status)})`;
}

/** Completed-turn workshop apprenticeship only; never reads final-world state. */
export function Apprenticeship({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const reading = readApprenticeship(snapshot, regions.length);
  const at = snapshot?.turn ?? currentTurn;
  if (reading.status !== "ok") return <section className="systems-section" aria-label="Workshop apprenticeship">
    <h3>Workshop apprenticeship</h3>
    <p className="systems-note">{reading.status === "absent"
      ? `Apprenticeship is not observed at snapshot ${at}.`
      : `The apprenticeship record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const city = new Map(record.sites.map((s) => [s.site, s.city_name]));
  const site = (id: number) => city.get(id) ?? `Site ${id}`;
  const outcomes = apprenticeshipOutcomes(record);
  const c = record.continuity;
  const completion = record.parameters.completion_turns;
  return <section className="systems-section" aria-label="Workshop apprenticeship">
    <h3>Workshop apprenticeship · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">A qualification is a dated record by person, not occupation skill. Qualified crew members of an operating workshop spend part of their crew time on upkeep against its wear and teach up to {show(record.parameters.per_mentor)} named apprentices each; a site with nobody qualified on its crew wears down. Apprentices give up part of their ordinary income; a firm with payroll pays a stipend from its cash.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Apprenticeship funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{apprenticeshipFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}
        <tr><td>Income given up by apprentices</td><td>{show(record.counters.income_forgone ?? 0)}</td></tr>
        <tr><td>Stipends paid (units)</td><td>{show((record.counters.stipends_paid ?? 0) / 1000)}</td></tr>
      </tbody>
    </table></div>
    {c === null ? <p className="systems-note">No apprenticeship pass was recorded in simulation turn {record.source_turn}; continuity this turn is unknown, not zero.</p> :
      <p className="systems-note" aria-label="Continuity">Retained by people: {c.qualified_alive} qualified alive anywhere, {c.qualified_elsewhere} of them away from every workshop region. Community teaching capacity: {c.qualified_in_site_regions} in workshop regions, {c.qualified_in_site_cities} in the workshop cities, {c.qualified_on_crews} on this turn's crews. {c.sites_without_qualified.length
        ? `Unmet: ${c.sites_without_qualified.map(site).join(", ")} ${c.sites_without_qualified.length === 1 ? "has" : "have"} no qualified person in the region.`
        : "Every site has a qualified person in its region."}</p>}
    {record.receipts === null ? null : record.receipts.length === 0 ? <p className="systems-note">No workshop site is open.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Apprenticeship sites at snapshot ${turn}`}>
        <thead><tr><th>Site</th><th>Region</th><th>Operating</th><th>Condition</th><th>Wear − upkeep</th><th>Qualified (city / on crew)</th><th>Mentors</th><th>Apprentices this turn</th><th>Stipends</th></tr></thead>
        <tbody>{record.receipts.map((r) => <tr key={r.site}>
          <td>{site(r.site)}{r.teaching_lost ? " · teaching lost" : ""}</td>
          <td><button type="button" className="systems-link" onClick={() => onSelectRegion(region(r.region))}>{region(r.region)}</button></td>
          <td>{r.operating ? "yes" : "no"}</td>
          <td>{show(r.condition_before)} → {show(r.condition_after)}</td>
          <td>{r.operating ? `${show(r.wear)} − ${show(r.upkeep_offset)} = ${show(r.net_wear)}` : "—"}</td>
          <td>{people(r.qualified_present)} / {people(r.qualified_on_crew)}</td>
          <td>{people(r.mentors)}</td>
          <td>{r.seats.length ? r.seats.map(seatText).join("; ") : `none (${r.seat_capacity} seats, ${r.eligible} eligible)`}</td>
          <td>{stipendText(r)}</td>
        </tr>)}</tbody>
      </table></div>}
    {record.apprenticeships.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open apprenticeships at snapshot ${turn}`}>
        <thead><tr><th>Apprentice</th><th>Site</th><th>Since</th><th>Attended</th><th>Missed in a row</th><th>Mentors</th><th>Income given up</th></tr></thead>
        <tbody>{record.apprenticeships.map((a) => <tr key={a.agent_id}>
          <td>{a.agent_id}{a.veteran ? " (veteran)" : ""}</td><td>{site(a.site)}</td><td>turn {a.started_turn}</td>
          <td>{a.attended}{completion ? ` of ${completion}` : ""}</td><td>{a.gap}</td><td>{people(a.mentors)}</td>
          <td>{show(a.income_forgone)}</td>
        </tr>)}</tbody>
      </table></div> : <p className="systems-note">No apprenticeship is open.</p>}
    {record.archive.length > 0 ? <p className="systems-note">Recent endings: {record.archive.slice(-8).map((a) =>
      `${a.agent_id} at ${site(a.site)} (turn ${a.ended_turn}, ${words(a.ended_reason)}${a.status === "completed" ? (a.granted ? ", qualified" : ", not granted") : ""})`).join("; ")}.</p> : null}
    {outcomes.missed.length || outcomes.ended.length ? <p className="systems-note">Interruptions: {outcomes.missed.map(([k, v]) => `${words(k)} ${v}`).join(", ") || "none"}. Endings: {outcomes.ended.map(([k, v]) => `${words(k)} ${v}`).join(", ") || "none"}.</p> : null}
    {record.qualifications.length > 0 ? <p className="systems-note">Qualified now: {record.qualifications.slice(0, 16).map((q) =>
      `${q.agent_id} (${q.via}, turn ${q.earned_turn}, lives in ${region(q.seen_region)})`).join("; ")}{record.qualifications.length > 16 ? `; and ${record.qualifications.length - 16} more` : ""}.</p> : null}
    {record.events.length > 0 ? <p className="systems-note">Continuity events: {record.events.slice(-6).map((e) =>
      `turn ${e.turn} ${words(e.kind)}${e.site !== null ? ` at ${site(e.site)}` : ""}${e.ids.length ? ` (${e.ids.join(", ")})` : ""}`).join("; ")}.</p> : null}
  </section>;
}
