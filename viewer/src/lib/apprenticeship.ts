import type { TurnSnapshot } from "../types";

/** A workshop qualification held by one person (``livelihoods.apprenticeship.qualifications``). */
export interface QualificationRecord {
  agent_id: number; earned_turn: number; site: number; settlement_id: number; region: number;
  via: "service" | "apprenticeship";
  /** Where the holder was last observed living (it travels with them). */
  seen_turn: number; seen_region: number; seen_settlement: number;
  status: "held" | "retired"; retired_turn: number | null; retired_reason: string | null;
}

/** One named apprentice (open, completed or ended). */
export interface ApprenticeRecord {
  agent_id: number; site: number; settlement_id: number; region: number; started_turn: number;
  veteran: boolean; attended: number; gap: number; interruptions: number; last_attended_turn: number | null;
  mentors: number[]; income_forgone: number; stipends: number;
  status: "active" | "completed" | "ended"; ended_turn: number | null; ended_reason: string | null;
  granted: boolean | null;
  /** Schema 2 (RS1 rules version 2) only: consecutive absent turns, where and how old it began, site
   * transfers, and attended turns on the planned crew or attached beside it. Absent in schema 1. */
  absent?: number; first_site?: number; entry_age?: number; transfers?: number; on_crew?: number; attached?: number;
}

/** A site's community: qualified people living in its region at the last observed turn. */
export interface SiteContinuityRecord {
  site: number; region: number; settlement_id: number; city_name: string; controller: number | null;
  present: number[]; observed_turn: number | null; last_present_turn: number | null;
  teaching_lost_turn: number | null;
}

export interface ContinuityEventRecord {
  turn: number; kind: "teaching_lost" | "teaching_restored" | "conquest"; site: number | null;
  region: number | null; ids: number[]; detail: Record<string, number | string | null>;
}

/** One open apprenticeship's turn at a site. */
export interface SeatRecord {
  agent_id: number; new: boolean; veteran: boolean; mentor: number | null;
  outcome: "attended" | "missed" | "ended"; reason: string | null; ending: string | null; share: number;
  /** Null: not attended or no wealth-phase observation (unknown, not zero). */
  income_forgone: number | null;
  stipend_due: number; stipend_paid: number; stipend_status: string | null;
  /** Schema 2: on the planned crew (training on crew time) or attached beside it; absent when not aboard. */
  aboard?: "crew" | "attached";
  /** Schema 2: the site this record transferred from this turn. */
  transferred_from?: number;
}

/** One open site's completed turn; work in person-turns of the crew's diverted time. */
export interface ApprenticeshipSiteReceipt {
  turn: number; site: number; region: number; settlement_id: number; controller: number | null;
  operating: boolean; crew: number[]; qualified_present: number[]; qualified_in_region: number[];
  qualified_on_crew: number[]; mentors: number[];
  crew_work: number; craft_work: number; upkeep_work: number; teaching_work: number;
  condition_before: number | null; wear: number; upkeep_offset: number; net_wear: number;
  condition_after: number | null; residents: number; candidates: number; eligible: number;
  seat_capacity: number; seats: SeatRecord[]; service_qualified: number[]; completed: number[];
  teaching_lost: boolean; stipend_status: string | null;
  /** Schema 2, operating site-turns only: who kept the site this turn. */
  graduates_on_crew?: number[]; covered?: boolean; full_offset?: boolean;
  offset_by_via?: { apprenticeship: number; service: number }; offset_by_graduates?: number;
}

/** Schema 2: a living person who completed an apprenticeship (granted or, in the control, not). */
export interface GraduateRecord {
  agent_id: number; completed_turn: number; site: number; region: number; granted: boolean;
  crew_turns: number; upkeep_offset: number; last_crew_turn: number | null;
}

export interface ContinuityTotals {
  turn: number; qualified_alive: number; qualified_in_site_regions: number; qualified_in_site_cities: number;
  qualified_on_crews: number; qualified_elsewhere: number; sites: number; sites_without_qualified: number[];
  service_in_progress: number;
}

export interface ApprenticeshipSnapshotRecord {
  /** 1: RS1 rules version 1 (a state saved before PL2); 2: rules version 2. */
  schema_version: 1 | 2; rules_version?: 2; stage: "RS1"; mode: "train" | "no_qualification"; source_turn: number;
  units: { stipend: string; work: string; milli: number };
  qualifications: QualificationRecord[]; retired: QualificationRecord[];
  apprenticeships: ApprenticeRecord[]; archive: ApprenticeRecord[];
  sites: SiteContinuityRecord[]; events: ContinuityEventRecord[];
  /** Null: no completed apprenticeship pass in the source turn (unknown, not zero). */
  receipts: ApprenticeshipSiteReceipt[] | null;
  continuity: ContinuityTotals | null;
  counters: Record<string, number>;
  parameters: Record<string, number>;
  /** Schema 2: living graduates, and the source turn's misses of records whose site is not open (null: unknown). */
  graduates?: GraduateRecord[];
  detached?: SeatRecord[] | null;
}

export type ApprenticeshipReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: ApprenticeshipSnapshotRecord };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const unit = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1;
const ids = (x: unknown, max: number): x is number[] => Array.isArray(x) && x.length <= max && x.every(count)
  && new Set(x).size === x.length;
const maybe = <T,>(check: (v: unknown) => v is T) => (x: unknown) => x === null || check(x);
const close = (a: number, b: number) => Math.abs(a - b) <= 1e-6;
const MODES = ["train", "no_qualification"];
const VIA = ["service", "apprenticeship"];
const END_REASONS = ["completed", "dropout", "died", "migrated", "departed", "occupation_changed", "site_closed",
  "remobilised", "pool_reset", "disabled", "service_qualified"];
const MISS_REASONS = ["unavailable", "no_mentor", "site_not_operating", "reservation_refused", "away"];
/** Rules version 2: presence by region replaces the city-box endings (away, dropout, migrated, departed);
 * a long absence ends a record; absent and no_room pause it, and a pause longer than ``max_pause``
 * consecutive missed turns of any reason ends it as ``stalled``. */
const END_REASONS_V2 = ["completed", "died", "occupation_changed", "site_closed", "remobilised", "pool_reset",
  "disabled", "service_qualified", "long_absence", "stalled"];
const MISS_REASONS_V2 = ["unavailable", "no_mentor", "site_not_operating", "reservation_refused", "absent", "no_room"];
const ABOARD = ["crew", "attached"];
/** Reason lists of a rules version (declaration order, append only). */
const rules = (version: number) => version === 2
  ? { end: END_REASONS_V2, miss: MISS_REASONS_V2 } : { end: END_REASONS, miss: MISS_REASONS };
const EVENTS = ["teaching_lost", "teaching_restored", "conquest"];
const STIPEND = ["paid", "partial", "no_payroll", "no_firm", "unpaid_labor", "no_cash", "absent"];

function validQualification(x: unknown, regions: number, held: boolean): boolean {
  return object(x) && count(x.agent_id) && count(x.earned_turn) && count(x.site) && count(x.settlement_id)
    && count(x.region) && x.region < regions && VIA.includes(x.via as string) && count(x.seen_turn)
    && count(x.seen_region) && x.seen_region < regions && count(x.seen_settlement)
    && (held ? x.status === "held" && x.retired_turn === null
      : x.status === "retired" && count(x.retired_turn) && typeof x.retired_reason === "string");
}

const V2_RECORD = ["absent", "first_site", "entry_age", "transfers", "on_crew", "attached"] as const;
const V2_RECEIPT = ["graduates_on_crew", "covered", "full_offset", "offset_by_via", "offset_by_graduates"] as const;
const V2_SEAT = ["aboard", "transferred_from"] as const;
const lacks = (x: Record<string, unknown>, keys: readonly string[]) => keys.every((k) => x[k] === undefined || x[k] === null);

function validApprentice(x: unknown, regions: number, open: boolean, p: Record<string, number>, version: number): boolean {
  if (!object(x) || !count(x.agent_id) || !count(x.site) || !count(x.region) || x.region >= regions
    || !count(x.started_turn) || typeof x.veteran !== "boolean" || !count(x.attended) || !count(x.gap)
    || !count(x.interruptions) || !maybe(count)(x.last_attended_turn) || !ids(x.mentors, 8)
    || !amount(x.income_forgone) || !count(x.stipends)) return false;
  if (version === 1) {
    if (!lacks(x, V2_RECORD)) return false;                      // a version-1 record has no version-2 fields
  } else {
    // Every attended turn was on the crew or attached; the age rule bounds entry.
    if (!V2_RECORD.every((k) => count(x[k])) || (x.on_crew as number) + (x.attached as number) !== x.attended
      || (p.max_entry_age !== undefined && (x.entry_age as number) > p.max_entry_age)) return false;
  }
  const { end } = rules(version);
  if (open) {
    const longAbsence = version === 2 ? p.long_absence_turns : undefined;
    return x.status === "active" && x.ended_turn === null
      && (version === 2 || p.max_gap === undefined || x.gap <= p.max_gap)
      && (longAbsence === undefined || (x.absent as number) <= longAbsence)
      && (version !== 2 || p.max_pause === undefined || x.gap <= p.max_pause)
      && (p.completion_turns === undefined || x.attended < p.completion_turns);
  }
  if (!count(x.ended_turn) || !end.includes(x.ended_reason as string)) return false;
  return x.status === "completed" ? x.ended_reason === "completed" && typeof x.granted === "boolean"
    : x.status === "ended" && x.ended_reason !== "completed";
}

function validSite(x: unknown, regions: number): boolean {
  return object(x) && count(x.site) && count(x.region) && x.region < regions && typeof x.city_name === "string"
    && maybe(count)(x.controller) && ids(x.present, 512) && maybe(count)(x.observed_turn)
    && maybe(count)(x.last_present_turn) && maybe(count)(x.teaching_lost_turn);
}

function validEvent(x: unknown, regions: number): boolean {
  return object(x) && count(x.turn) && EVENTS.includes(x.kind as string) && maybe(count)(x.site)
    && (x.region === null || (count(x.region) && x.region < regions)) && ids(x.ids, 512) && object(x.detail);
}


function seatProblem(x: unknown, version: number, p: Record<string, number>): string | null {
  if (!object(x) || !count(x.agent_id) || typeof x.new !== "boolean" || typeof x.veteran !== "boolean"
    || !maybe(count)(x.mentor) || !unit(x.share) || !maybe(amount)(x.income_forgone) || !count(x.stipend_due)
    || !count(x.stipend_paid) || x.stipend_paid > x.stipend_due
    || (x.stipend_status !== null && !STIPEND.includes(x.stipend_status as string))) return "malformed site receipt";
  const { end, miss } = rules(version);
  if (version === 1) {
    if (!lacks(x, V2_SEAT)) return "malformed site receipt";
  } else if (!(x.aboard === undefined || x.aboard === null || ABOARD.includes(x.aboard as string))
    || !(x.transferred_from === undefined || x.transferred_from === null || count(x.transferred_from))) {
    return "malformed site receipt";
  }
  if (x.outcome === "attended") {
    if (!count(x.mentor) || !(x.ending === null || x.ending === "completed" || x.ending === "service_qualified"))
      return "malformed site receipt";
    if (version === 1) return x.share > 0 ? null : "malformed site receipt";
    // Version 2: a crew apprentice trains on crew time (nothing reserved, withheld or paid);
    // an attached one is reserved for the apprentice fraction beside the crew.
    if (x.aboard === "crew") return x.share === 0 && x.stipend_due === 0 && x.income_forgone === null
      ? null : "a crew apprentice was reserved or paid beside the crew";
    if (x.aboard === "attached") return x.share > 0 && (p.apprentice_fraction === undefined || close(x.share, p.apprentice_fraction))
      ? null : "an attached apprentice was not reserved";
    return "an attended apprentice was not aboard";
  }
  if (x.outcome === "missed") return miss.includes(x.reason as string) && x.stipend_due === 0
    && x.income_forgone === null && (x.ending === null || end.includes(x.ending as string)) ? null : "malformed site receipt";
  return x.outcome === "ended" && end.includes(x.reason as string) && x.stipend_due === 0 ? null : "malformed site receipt";
}

function validReceipt(x: unknown, regions: number, source: number, p: Record<string, number>, version: number): string | null {
  if (!object(x) || x.turn !== source || !count(x.site) || !count(x.region) || x.region >= regions
    || typeof x.operating !== "boolean" || !ids(x.crew, 8) || !ids(x.qualified_present, 512)
    || !ids(x.qualified_in_region, 512) || !ids(x.qualified_on_crew, 8) || !ids(x.mentors, 8)
    || ![x.crew_work, x.craft_work, x.upkeep_work, x.teaching_work, x.wear, x.upkeep_offset, x.net_wear].every(amount)
    || !maybe(unit)(x.condition_before) || !maybe(unit)(x.condition_after) || !count(x.residents)
    || !count(x.candidates) || !count(x.eligible) || !count(x.seat_capacity) || !Array.isArray(x.seats)
    || !ids(x.service_qualified, 8) || !ids(x.completed, 8)
    || typeof x.teaching_lost !== "boolean") return "malformed site receipt";
  for (const seat of x.seats) {
    const why = seatProblem(seat, version, p);
    if (why) return why;
  }
  const crew = new Set(x.crew as number[]);
  const onCrew = new Set(x.qualified_on_crew as number[]);
  if (!(x.qualified_on_crew as number[]).every((a) => crew.has(a))
    || !(x.mentors as number[]).every((a) => onCrew.has(a))) return "a mentor is not a qualified crew member";
  const seats = x.seats as SeatRecord[];
  if (new Set(seats.map((s) => s.agent_id)).size !== seats.length) return "a person holds two seats";
  if (seats.some((s) => s.share > 0 && crew.has(s.agent_id))) return "an apprentice is also on the crew";
  if (seats.some((s) => s.aboard === "crew" && !crew.has(s.agent_id))) return "a crew apprentice is not on the crew";
  if (seats.some((s) => s.outcome === "attended" && !(x.mentors as number[]).includes(s.mentor as number)))
    return "an apprentice was taught by someone who is not a mentor";
  const perMentor = p.per_mentor ?? 2;
  if (seats.filter((s) => s.outcome === "attended").length > perMentor * (x.mentors as number[]).length)
    return "more apprentices taught than mentors can teach";
  if ((x.upkeep_offset as number) > (x.wear as number) + 1e-9
    || !close(x.net_wear as number, (x.wear as number) - (x.upkeep_offset as number))) return "wear does not close";
  if (x.operating && !close((x.craft_work as number) + (x.upkeep_work as number) + (x.teaching_work as number),
    x.crew_work as number)) return "crew time does not close";
  if (!x.operating && ((x.crew as number[]).length || x.wear || x.upkeep_work || x.teaching_work
    || seats.some((s) => s.outcome === "attended"))) return "a site that did not operate shows work";
  if (version === 1) return lacks(x, V2_RECEIPT) ? null : "malformed site receipt";
  // Version 2 useful-work records: present exactly on operating site-turns, and closing.
  if (!x.operating) return lacks(x, V2_RECEIPT) ? null : "a site that did not operate shows useful work";
  const via = x.offset_by_via;
  if (!ids(x.graduates_on_crew, 8) || typeof x.covered !== "boolean" || typeof x.full_offset !== "boolean"
    || !object(via) || !amount(via.apprenticeship) || !amount(via.service) || Object.keys(via).length !== 2
    || !amount(x.offset_by_graduates)) return "malformed useful-work record";
  if (!(x.graduates_on_crew as number[]).every((a) => crew.has(a))) return "a graduate counted aboard is not on the crew";
  if (x.covered !== onCrew.size > 0) return "coverage disagrees with the qualified crew";
  if (x.full_offset !== ((x.upkeep_offset as number) >= (x.wear as number))) return "the full-offset flag disagrees with the wear";
  if (!close(via.apprenticeship + via.service, x.upkeep_offset as number)
    || (x.offset_by_graduates as number) > (x.upkeep_offset as number) + 1e-9) return "the upkeep offset by route does not close";
  return null;
}

function validGraduate(x: unknown, regions: number, source: number, train: boolean): boolean {
  return object(x) && count(x.agent_id) && count(x.completed_turn) && x.completed_turn <= source && count(x.site)
    && count(x.region) && x.region < regions && typeof x.granted === "boolean" && (train || x.granted === false)
    && count(x.crew_turns) && amount(x.upkeep_offset) && maybe(count)(x.last_crew_turn)
    && (x.last_crew_turn === null || ((x.last_crew_turn as number) > x.completed_turn && (x.last_crew_turn as number) <= source))
    && (x.crew_turns === 0) === (x.last_crew_turn === null);
}

/** Strict reading: absent, malformed (with the reason) or a dated, closing record (schema 1 or 2). */
export function readApprenticeship(snapshot: TurnSnapshot | null, regionCount: number): ApprenticeshipReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.apprenticeship === undefined) return { status: "absent" };
  if (livelihoods.schema_version !== 1) return { status: "malformed", reason: "unknown livelihoods schema" };
  const x = livelihoods.apprenticeship;
  const bad = (reason: string): ApprenticeshipReading => ({ status: "malformed", reason });
  if (!object(x) || (x.schema_version !== 1 && x.schema_version !== 2) || x.stage !== "RS1"
    || !MODES.includes(x.mode as string)) return bad("unknown apprenticeship schema");
  const version = x.schema_version as number;
  // Schema 2 is written by RS1 rules version 2 and names it; schema 1 carries no version-2 field.
  if (version === 2 ? x.rules_version !== 2 : !lacks(x, ["rules_version", "graduates", "detached"]))
    return bad("unknown apprenticeship rules version");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  if (!object(x.parameters) || !Object.values(x.parameters).every(finite) || !object(x.counters)
    || !Object.values(x.counters).every(amount)) return bad("malformed counters or parameters");
  const p = x.parameters as Record<string, number>;
  if (!Array.isArray(x.qualifications) || x.qualifications.length > 512
    || !x.qualifications.every((q) => validQualification(q, regionCount, true))
    || new Set(x.qualifications.map((q) => (q as QualificationRecord).agent_id)).size !== x.qualifications.length)
    return bad("malformed qualifications");
  if (!Array.isArray(x.retired) || x.retired.length > 64
    || !x.retired.every((q) => validQualification(q, regionCount, false))) return bad("malformed retired records");
  if (!Array.isArray(x.apprenticeships) || x.apprenticeships.length > 4 * (p.per_site ?? 4)
    || !x.apprenticeships.every((a) => validApprentice(a, regionCount, true, p, version))) return bad("malformed apprenticeships");
  const held = new Set((x.qualifications as QualificationRecord[]).map((q) => q.agent_id));
  if ((x.apprenticeships as ApprenticeRecord[]).some((a) => held.has(a.agent_id)))
    return bad("a qualified person is still an apprentice");
  if (!Array.isArray(x.archive) || x.archive.length > 64
    || !x.archive.every((a) => validApprentice(a, regionCount, false, p, version))) return bad("malformed archive");
  if (x.mode === "no_qualification" && (x.archive as ApprenticeRecord[])
    .some((a) => a.ended_turn === x.source_turn && a.granted === true)) return bad("a control completion was granted");
  if (!Array.isArray(x.sites) || x.sites.length > 4 || !x.sites.every((s) => validSite(s, regionCount)))
    return bad("malformed site continuity");
  if (!Array.isArray(x.events) || x.events.length > 64 || !x.events.every((e) => validEvent(e, regionCount)))
    return bad("malformed events");
  if (x.receipts !== null) {
    if (!Array.isArray(x.receipts) || x.receipts.length > 4) return bad("malformed receipts");
    for (const r of x.receipts) {
      const why = validReceipt(r, regionCount, x.source_turn, p, version);
      if (why) return bad(why);
    }
  }
  if (version === 2) {
    if (!Array.isArray(x.graduates) || x.graduates.length > 512
      || !x.graduates.every((g) => validGraduate(g, regionCount, x.source_turn as number, x.mode === "train"))
      || new Set(x.graduates.map((g) => (g as GraduateRecord).agent_id)).size !== x.graduates.length)
      return bad("malformed graduates");
    const open = new Set((x.apprenticeships as ApprenticeRecord[]).map((a) => a.agent_id));
    if ((x.graduates as GraduateRecord[]).some((g) => open.has(g.agent_id))) return bad("a graduate is still an apprentice");
    // Detached misses belong to the same completed pass as the receipts.
    if ((x.detached === null) !== (x.receipts === null)) return bad("detached records without the turn's receipts");
    if (x.detached !== null) {
      if (!Array.isArray(x.detached) || x.detached.length > 4 * (p.per_site ?? 4)) return bad("malformed detached records");
      for (const seat of x.detached) {
        if (seatProblem(seat, 2, p) || (seat as SeatRecord).outcome !== "missed"
          || !["absent", "no_room"].includes((seat as SeatRecord).reason as string)) return bad("malformed detached records");
      }
      const seated = new Set((x.receipts as ApprenticeshipSiteReceipt[]).flatMap((r) => r.seats.map((s) => s.agent_id)));
      if ((x.detached as SeatRecord[]).some((s) => seated.has(s.agent_id))) return bad("a detached apprentice also holds a seat");
    }
  }
  if (x.continuity !== null) {
    const c = x.continuity;
    if (!object(c) || c.turn !== x.source_turn || !count(c.qualified_alive) || !count(c.qualified_in_site_regions)
      || !count(c.qualified_in_site_cities) || !count(c.qualified_on_crews) || !count(c.qualified_elsewhere)
      || !count(c.sites) || !ids(c.sites_without_qualified, 4) || !count(c.service_in_progress)
      || c.qualified_alive !== (x.qualifications as unknown[]).length
      || c.qualified_in_site_regions + c.qualified_elsewhere !== c.qualified_alive) return bad("continuity does not close");
  }
  return { status: "ok", record: x as unknown as ApprenticeshipSnapshotRecord };
}

/** The record, or null when absent or malformed. */
export function apprenticeshipAt(snapshot: TurnSnapshot | null, regionCount: number): ApprenticeshipSnapshotRecord | null {
  const reading = readApprenticeship(snapshot, regionCount);
  return reading.status === "ok" ? reading.record : null;
}

/** Lifetime activation funnel from the scalar counters (zero only once the record exists). */
export function apprenticeshipFunnel(record: ApprenticeshipSnapshotRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Site-turns observed", c("site_turns")],
    ["Operating site-turns", c("operating_site_turns")],
    ["Crew-turns served (unqualified)", c("crew_turns_served")],
    ["Qualified by service", c("qualified_service")],
    ["Mentor-turns (taught at least one)", c("mentor_turns")],
    ["Seats offered (mentor capacity)", c("seats_offered")],
    ["Apprentices enrolled", c("enrolled")],
    ["Apprentice-turns attended", c("apprentice_turns_attended")],
    ["Completions", c("completions")],
    ["Qualified by apprenticeship", c("qualified_apprenticeship")],
  ];
}

/** Schema 2: attendance by how the apprentice was aboard, and the useful work that kept the sites. */
export function usefulWork(record: ApprenticeshipSnapshotRecord): Array<[string, number]> | null {
  if (record.schema_version !== 2) return null;
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Apprentice-turns on the crew (crew time)", c("apprentice_turns_on_crew")],
    ["Apprentice-turns attached beside the crew", c("apprentice_turns_attached")],
    ["Transfers to another site with progress kept", c("transferred")],
    ["Operating site-turns covered by a qualified member", c("covered_site_turns")],
    ["Operating site-turns with the wear fully offset", c("full_offset_site_turns")],
    ["Qualified crew-turns", c("qualified_crew_turns")],
    ["Graduate crew-turns", c("graduate_crew_turns")],
    ["Upkeep offset by service qualifications", c("upkeep_offset_service")],
    ["Upkeep offset by apprenticeship qualifications", c("upkeep_offset_apprenticeship")],
    ["Upkeep offset by graduates", c("upkeep_offset_graduates")],
    ["Graduates (completed)", c("graduates")],
    ["Graduates who died", c("graduates_died")],
  ];
}

/** Interruptions and endings by reason, from the counters (non-zero only). */
export function apprenticeshipOutcomes(record: ApprenticeshipSnapshotRecord): {
  missed: Array<[string, number]>; ended: Array<[string, number]>;
} {
  const { end, miss } = rules(record.schema_version);
  const pick = (prefix: string, keys: string[]) => keys
    .map((k): [string, number] => [k, record.counters[prefix + k] ?? 0]).filter(([, v]) => v > 0);
  return { missed: pick("miss_", miss), ended: pick("end_", end) };
}
