import type { Bundle, TurnSnapshot } from "../../types";
import {
  apprenticeshipFunnel, apprenticeshipOutcomes, readApprenticeship, usefulWork, type ApprenticeshipSiteReceipt,
  type SeatRecord,
} from "../../lib/apprenticeship";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
const people = (list: number[]) => (list.length ? list.join(", ") : "none");
const MODE_NOTE: Record<string, string> = {
  train: "Train mode: an apprentice who attends the required turns earns a workshop qualification, kept for life wherever they live.",
  no_qualification: "No-qualification control: apprentices attend, give up the same income and their mentors spend the same time, and completions are recorded, but completing grants no qualification. Service qualifications accrue as in train mode.",
};

const RULES_NOTE: Record<number, string> = {
  1: "RS1 rules version 1 (a state saved before PL2): presence in the workshop's city, a seat reserved before the crew, and a dropout after too many misses.",
  2: "RS1 rules version 2: presence anywhere in the site's region; an apprentice trains on the crew (crew time) or attached beside it (reserved, with income withheld and a stipend from a paying firm); progress travels to another site's region; missed turns pause it, and only a long absence or a long pause (stalled) ends it.",
};

function seatText(s: SeatRecord): string {
  const tag = `${s.agent_id}${s.veteran ? " (veteran)" : ""}${s.new ? " new" : ""}${s.transferred_from != null ? ` (from site ${s.transferred_from})` : ""}`;
  if (s.outcome === "attended") {
    const done = s.ending ? `, ${words(s.ending)}` : "";
    if (s.aboard === "crew") return `${tag}: on the crew, taught by ${s.mentor}${done}`;
    const how = s.aboard === "attached" ? "attached, " : "";
    return `${tag}: ${how}taught by ${s.mentor}, income given up ${show(s.income_forgone)}${done}`;
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
  const v2 = record.schema_version === 2;
  const useful = usefulWork(record);
  const keep = (r: ApprenticeshipSiteReceipt) => !r.operating || r.covered === undefined ? "—"
    : `${r.covered ? "covered" : "nobody qualified aboard"}${r.full_offset ? ", wear fully offset" : ""}; offset by service ${show(r.offset_by_via?.service)}, by apprenticeship ${show(r.offset_by_via?.apprenticeship)}${r.graduates_on_crew?.length ? `; graduates aboard ${people(r.graduates_on_crew)}` : ""}`;
  return <section className="systems-section" aria-label="Workshop apprenticeship">
    <h3>Workshop apprenticeship · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">{RULES_NOTE[record.schema_version]}</p>
    <p className="systems-note">A qualification is a dated record by person, not occupation skill. Qualified crew members of an operating workshop spend part of their crew time on upkeep against its wear and teach up to {show(record.parameters.per_mentor)} named apprentices each; a site with nobody qualified on its crew wears down. Apprentices give up part of their ordinary income; a firm with payroll pays a stipend from its cash.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Apprenticeship funnel at snapshot ${turn}`}>
      <thead><tr><th>Stage (lifetime)</th><th>Count</th></tr></thead>
      <tbody>{apprenticeshipFunnel(record).map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}
        <tr><td>Income given up by apprentices</td><td>{show(record.counters.income_forgone ?? 0)}</td></tr>
        <tr><td>Stipends paid (units)</td><td>{show((record.counters.stipends_paid ?? 0) / 1000)}</td></tr>
      </tbody>
    </table></div>
    {useful !== null ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Apprenticeship useful work to snapshot ${turn}`}>
      <thead><tr><th>Who kept the sites (lifetime)</th><th>Amount</th></tr></thead>
      <tbody>{useful.map(([label, value]) => <tr key={label}><td>{label}</td><td>{show(value)}</td></tr>)}</tbody>
    </table></div> : null}
    {c === null ? <p className="systems-note">No apprenticeship pass was recorded in simulation turn {record.source_turn}; continuity this turn is unknown, not zero.</p> :
      <p className="systems-note" aria-label="Continuity">Retained by people: {c.qualified_alive} qualified alive anywhere, {c.qualified_elsewhere} of them away from every workshop region. Community teaching capacity: {c.qualified_in_site_regions} in workshop regions, {c.qualified_in_site_cities} in the workshop cities, {c.qualified_on_crews} on this turn's crews. {c.sites_without_qualified.length
        ? `Unmet: ${c.sites_without_qualified.map(site).join(", ")} ${c.sites_without_qualified.length === 1 ? "has" : "have"} no qualified person in the region.`
        : "Every site has a qualified person in its region."}</p>}
    {record.receipts === null ? null : record.receipts.length === 0 ? <p className="systems-note">No workshop site is open.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Apprenticeship sites at snapshot ${turn}`}>
        <thead><tr><th>Site</th><th>Region</th><th>Operating</th><th>Condition</th><th>Wear − upkeep</th><th>Qualified (city / on crew)</th><th>Mentors</th><th>Apprentices this turn</th><th>Stipends</th>{v2 ? <th>Who kept it</th> : null}</tr></thead>
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
          {v2 ? <td>{keep(r)}</td> : null}
        </tr>)}</tbody>
      </table></div>}
    {record.apprenticeships.length > 0 ?
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Open apprenticeships at snapshot ${turn}`}>
        <thead><tr><th>Apprentice</th><th>Site</th><th>Since</th><th>Attended</th><th>Missed in a row</th>{v2 ? <><th>Absent in a row</th><th>On crew / attached</th><th>Transfers</th></> : null}<th>Mentors</th><th>Income given up</th></tr></thead>
        <tbody>{record.apprenticeships.map((a) => <tr key={a.agent_id}>
          <td>{a.agent_id}{a.veteran ? " (veteran)" : ""}{v2 && a.entry_age !== undefined ? `, entered at ${a.entry_age}` : ""}</td><td>{site(a.site)}</td><td>turn {a.started_turn}</td>
          <td>{a.attended}{completion ? ` of ${completion}` : ""}</td><td>{a.gap}{v2 && record.parameters.max_pause !== undefined ? ` (stalls after ${record.parameters.max_pause})` : ""}</td>
          {v2 ? <><td>{show(a.absent)}{record.parameters.long_absence_turns !== undefined ? ` (ends after ${record.parameters.long_absence_turns})` : ""}</td>
            <td>{show(a.on_crew)} / {show(a.attached)}</td><td>{show(a.transfers)}</td></> : null}
          <td>{people(a.mentors)}</td>
          <td>{show(a.income_forgone)}</td>
        </tr>)}</tbody>
      </table></div> : <p className="systems-note">No apprenticeship is open.</p>}
    {record.archive.length > 0 ? <p className="systems-note">Recent endings: {record.archive.slice(-8).map((a) =>
      `${a.agent_id} at ${site(a.site)} (turn ${a.ended_turn}, ${words(a.ended_reason)}${a.status === "completed" ? (a.granted ? ", qualified" : ", not granted") : ""})`).join("; ")}.</p> : null}
    {outcomes.missed.length || outcomes.ended.length ? <p className="systems-note">Interruptions: {outcomes.missed.map(([k, v]) => `${words(k)} ${v}`).join(", ") || "none"}. Endings: {outcomes.ended.map(([k, v]) => `${words(k)} ${v}`).join(", ") || "none"}.</p> : null}
    {v2 && record.receipts !== null && record.detached ? (record.detached.length ? <p className="systems-note">Away from every open site this turn: {record.detached.map((s) =>
      `${s.agent_id} (${words(s.reason)}${s.ending ? `, ${words(s.ending)}` : ""})`).join("; ")}.</p> : null) : null}
    {v2 && record.graduates ? (record.graduates.length ? <p className="systems-note">Living graduates: {record.graduates.slice(0, 16).map((g) =>
      `${g.agent_id} (completed turn ${g.completed_turn} at ${site(g.site)}, ${g.granted ? "qualified" : "not granted"}; ${g.crew_turns} crew-turns since, upkeep ${show(g.upkeep_offset)})`).join("; ")}{record.graduates.length > 16 ? `; and ${record.graduates.length - 16} more` : ""}.</p>
      : <p className="systems-note">No living graduate.</p>) : null}
    {record.qualifications.length > 0 ? <p className="systems-note">Qualified now: {record.qualifications.slice(0, 16).map((q) =>
      `${q.agent_id} (${q.via}, turn ${q.earned_turn}, lives in ${region(q.seen_region)})`).join("; ")}{record.qualifications.length > 16 ? `; and ${record.qualifications.length - 16} more` : ""}.</p> : null}
    {record.events.length > 0 ? <p className="systems-note">Continuity events: {record.events.slice(-6).map((e) =>
      `turn ${e.turn} ${words(e.kind)}${e.site !== null ? ` at ${site(e.site)}` : ""}${e.ids.length ? ` (${e.ids.join(", ")})` : ""}`).join("; ")}.</p> : null}
  </section>;
}
