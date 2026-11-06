import type { Bundle, TurnSnapshot } from "../../types";
import {
  COMMONS_REASONS, RETAIL_MODE_LABEL, RETAIL_STATUSES, RISKS, commonsOf, commonsShare, flowOf, ownedTitle, readHouseholdRetail, riskTotals,
  type HouseholdRetailRecord, type RetailRegionFrame, type Risk,
} from "../../lib/householdRetail";
import {
  COHORT_GROUPS, COHORT_LABEL, readCohorts, readWarLosses, rulesVersion, WAR_CAUSES, type CohortField, type CohortGroup,
} from "../../lib/householdRetailEvidence";

const number = (value: number, digits = 3) =>
  (Math.abs(value) < 5e-7 ? 0 : value).toLocaleString(undefined, { maximumFractionDigits: digits });
const show = (value: number | null | undefined, digits = 3) => value === null || value === undefined ? "Unknown" : number(value, digits);
/** Milli-food as food units (1000 = one food unit = two rations at the default ration). */
const food = (milli: number | null | undefined) => milli === null || milli === undefined ? "Unknown" : number(milli / 1000);
/** Milli-units as wealth units. */
const coins = (milli: number | null | undefined) => milli === null || milli === undefined ? "Unknown" : number(milli / 1000);
const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");

const MODE_NOTE: Record<string, string> = {
  retail: "Retail: in each pilot region most of every new harvest belongs to its farmers by stable id. Owners' households eat their own food first, within their fair share, and sell the rest to neighbours at the clamped market price; buyers pay from their wealth, and farmers' ordinary farm income is replaced by what they sell. The commons and granary releases stay free, means-tested first.",
  no_relief: "No-relief control (what relief protects): the whole harvest is titled, so no share stays commons, and the commons are allocated by the food-allocation rule with no means test. The rest is as retail; compare with a retail run to see what the commons share and the means test protect.",
  free_exchange: "Free-exchange control (ownership without cash): the same title and the same rounds at price 0. Nobody pays, farmers keep their ordinary farm income, and granaries take owners' grain without paying them; compare with a retail run to see what payment and income replacement do.",
  record_only: "Record-only control (identity control, nothing applied): the pilot boundary is kept and what retail would title and price is recorded, but no food is owned, sold or paid and no income changes. The world is the food-allocation run's alone.",
};
const BOUNDARY_NOTE: Record<string, string> = {
  market: "market: each ruling civilization's capital region, from the turn it first qualifies",
  paid_work: "paid_work: regions where paid work has been done (an open workshop firm, a paid repair or granary crew, or the home of a paid woodcutting crew)",
  all: "all: every controlled region (a stress setting)",
  schedule: "schedule: the regions of a frozen schedule (another run's recorded enrollment, for example)",
};
const CAUSE_LABEL: Record<string, string> = { conquest: "conquest", siege: "siege turn", occupation: "occupation start" };
const ACTOR_ROLE: Record<string, string> = { conquest: "conqueror", siege: "besieger", occupation: "occupier" };

/** The turn's cohorts summed over provisioned regions; a field is unknown when any region's is. */
function cohortTotals(record: HouseholdRetailRecord) {
  const totals = {} as Record<CohortGroup, Record<CohortField, number | null>>;
  const unknown: string[] = [];
  const states = { disabled: 0, absent: 0, malformed: [] as string[], ok: 0 };
  for (const g of COHORT_GROUPS) {
    totals[g] = { persons: 0, priced_out: 0, paid_milli: 0, refunded_milli: 0, credited_milli: 0, income_replaced: 0, wages_milli: 0 };
  }
  for (const r of record.regions ?? []) {
    const reading = readCohorts(record, r);
    if (reading.status !== "ok") {
      if (reading.status === "malformed") states.malformed.push(`region ${r.region}: ${reading.reason}`);
      else if (reading.status !== "unobserved") states[reading.status] += 1;
      continue;
    }
    states.ok += 1;
    for (const g of COHORT_GROUPS) {
      for (const f of Object.keys(totals[g]) as CohortField[]) {
        const v = reading.cohorts.groups[g][f];
        totals[g][f] = v === null || totals[g][f] === null ? null : (totals[g][f] as number) + v;
      }
    }
    for (const [f, why] of Object.entries(reading.cohorts.unknown)) unknown.push(`${r.region}|${f.replace(/_/g, " ")}: ${why}`);
  }
  return { totals, unknown, states };
}
const RISK_LABEL: Record<Risk, string> = {
  priced_out: "Priced out (cash ran out)",
  offer_short: "Offer short (not enough food on offer)",
  withheld_dead: "Withheld (a dead owner's claim held for the heirs)",
};
const RISK_HEAD: Record<Risk, string> = { priced_out: "Priced out", offer_short: "Offer short", withheld_dead: "Withheld for heirs" };
const RISK_ABSENT: Record<Risk, string> = {
  priced_out: "priced out", offer_short: "short of the offer", withheld_dead: "short of a claim withheld for heirs",
};
const RISK_SHORT: Record<Risk, string> = { priced_out: "priced out", offer_short: "offer short", withheld_dead: "withheld for heirs" };
const plural = (n: number, one: string, many = `${one}s`) => `${number(n)} ${n === 1 ? one : many}`;
const STATUS_LABEL: Record<string, string> = {
  fed: "fed", priced_out: "priced out", offer_short: "offer short", withheld_dead: "withheld (dead owner's claim)",
};
const COMMONS_LABEL: Record<string, string> = {
  untitled: "no farmer to title", claims_refused: "claims cap", escheat: "no heir", pilot_closed: "left the pilot",
  pool_reset: "native pool rebuilt", switch_off: "switched off",
};

function riskCell(p: RetailRegionFrame["provisioning"], k: Risk): string {
  if (p === null) return "Unknown";
  if (!p[`${k}_persons`]) return "none";
  return `${p[`${k}_children`]} · ${p[`${k}_persons`]} · ${p[`${k}_households`]} (${number(p[`${k}_deficit`])})`;
}

function riskSentence(record: HouseholdRetailRecord): string | null {
  const totals = riskTotals(record);
  if (totals === null) return null;
  const provisioned = (record.regions ?? []).filter((r) => r.provisioning !== null);
  const persons = provisioned.reduce((a, r) => a + r.provisioning!.persons, 0);
  const children = provisioned.reduce((a, r) => a + r.provisioning!.children, 0);
  const head = `${plural(persons, "person", "people")} (${plural(children, "child", "children")}) were provisioned in ${plural(provisioned.length, "pilot region")}.`;
  const below = RISKS.filter((k) => totals[k].persons > 0);
  if (!below.length) return `${head} Everyone reached their fair share.`;
  const absent = RISKS.filter((k) => totals[k].persons === 0);
  return `${head} Below their fair share: ${below.map((k) => `${RISK_SHORT[k]}, ${plural(totals[k].children, "child", "children")} among ${plural(totals[k].persons, "person", "people")} in ${plural(totals[k].households, "household")} (deficit ${number(totals[k].deficit)} rations)`).join("; ")}.${absent.length ? ` Nobody was ${absent.map((k) => RISK_ABSENT[k]).join(" or ")}.` : ""}`;
}

function incomeCell(record: HouseholdRetailRecord, r: RetailRegionFrame): string {
  if (record.mode === "free_exchange") return "kept (not replaced)";
  if (record.mode === "record_only") return "not replaced";
  if (r.provisioning === null) return "not replaced (not provisioned)";
  if (r.income_replaced !== null) return `${number(r.income_replaced)} (${r.income_rows} farmers)`;
  return r.provisioning !== null && record.income && Object.keys(record.income).length ? "none (no farmer rows)" : "Unknown";
}

function priceCell(record: HouseholdRetailRecord, r: RetailRegionFrame): string {
  if (r.price_milli === null) return "not installed";
  if (record.mode === "free_exchange") return "not charged";
  return coins(r.price_milli);
}

/** Completed-turn household retail only; never reads final-world state. */
export function HouseholdRetail({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const reading = readHouseholdRetail(snapshot, regions.length);
  const at = snapshot?.turn ?? currentTurn;
  if (reading.status !== "ok") return <section className="systems-section" aria-label="Household retail">
    <h3>Household retail</h3>
    <p className="systems-note">{reading.status === "absent"
      ? `Household retail is not observed at snapshot ${at}.`
      : `The household retail record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const p = record.parameters;
  const c = (key: string) => record.counters[key] ?? 0;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const link = (index: number) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(region(index))}>{region(index)}</button>;
  const frames = record.regions;
  const control = record.mode === "record_only";
  const thisTurn = record.log.filter((e) => e.turn === record.source_turn);
  const closed = new Set(thisTurn.filter((e) => e.kind === "pilot_closed").map((e) => e.region));
  const name = (r: RetailRegionFrame) => <>{link(r.region)}{r.opened_turn === record.source_turn ? " (joined this turn)" : ""}
    {closed.has(r.region) ? " (left the pilot)" : ""}</>;
  const provisioned = (frames ?? []).filter((r) => r.provisioning !== null);
  const unprovisioned = control ? [] : (frames ?? []).filter((r) => r.provisioning === null);
  const atRisk = provisioned.filter((r) => RISKS.some((k) => r.provisioning![`${k}_persons`] > 0));
  /** Only the causes someone was short of this turn get a column (the sentence names the others as none). */
  const causes = RISKS.filter((k) => atRisk.some((r) => r.provisioning![`${k}_persons`] > 0));
  const sampled = (record.sample ?? []).filter((s) => s[5] !== 0);
  const money = record.money ?? {};
  const procurement = "procurement_flows" in money ? money : null;
  const counts = (kind: string) => thisTurn.filter((e) => e.kind === kind).length;
  const notable = record.log.filter((e) => !["inherited", "escheat"].includes(e.kind)).slice(-8);
  const theta = p.theta;
  const v2 = rulesVersion(record) === 2;
  const keys = record as unknown as Record<string, unknown>;
  /** RL4 counters: absent from a version-2 record written before the cut (A5: no opened_turn) is not
   * recorded, not 0; the commons' share came with the pro-rata cut (S1: intervals). */
  const aboveCap = !("opened_turn" in keys) ? "not recorded (written before the storage-cap cut)"
    : `${food(c("owned_grain_above_cap_milli"))} · ${"intervals" in keys ? food(c("commons_grain_above_cap_milli")) : "not recorded (written before the pro-rata cut)"}`;
  const capCut = (r: RetailRegionFrame) => (r as unknown as { cap_cut?: { owned_milli: number; commons_milli: number } }).cap_cut ?? null;
  const schedule = (record as unknown as { schedule?: { sha256: string; turns: Record<string, number | [number, number | null][]> } }).schedule;
  /** S1: exact intervals (a region also leaves when its interval ends) or the first-turn format
   * (each region from its opening turn), which cannot replay a region its source closed. */
  const intervalSchedule = schedule ? Object.values(schedule.turns).some((v) => Array.isArray(v)) : false;
  const scheduleNote = !schedule ? "" : ` (${intervalSchedule
    ? "exact intervals: each region only within its intervals"
    : "first-turn schedule, each region from its opening turn: approximate, it cannot replay a region its source closed"}; ${plural(Object.keys(schedule.turns).length, "region")}, schedule sha256 ${schedule.sha256.slice(0, 12)})`;
  const leaves = intervalSchedule ? "a region leaves when it has no controller or its schedule interval ends"
    : "a region leaves only when it has no controller";
  const cohorts = cohortTotals(record);
  const cell = (v: number | null, f: CohortField) => v === null ? "Unknown"
    : f === "persons" || f === "priced_out" ? number(v) : f === "income_replaced" ? number(v) : coins(v);
  const cohortSection = provisioned.length === 0 ? null : !v2
    ? <p className="systems-note">Household groups (crew members, their children, children alone, non-farm adults, other farm households) are recorded under retail rules version 2 only; this record is version 1, so who bought and who was priced out by group is not recorded (unknown, not zero).</p>
    : cohorts.states.ok === 0 && cohorts.states.malformed.length === 0
      ? <p className="systems-note">This run recorded no household groups (a rules-version-2 record written before them): unknown, not zero.</p>
      : <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Household groups at snapshot ${turn}`}>
          <caption>Household groups of the people provisioned in {plural(cohorts.states.ok, "pilot region")}: persons, priced out, money (paid · refunded · credited for food sold), farm income replaced, crew wages. Unknown: a value the run could not attribute exactly (reasons below), never zero.</caption>
          <thead><tr><th>Group</th><th>Persons</th><th>Priced out</th><th>Paid · refunded</th><th>Credited</th><th>Income replaced</th><th>Crew wages</th></tr></thead>
          <tbody>{COHORT_GROUPS.map((g) => <tr key={g}>
            <td>{COHORT_LABEL[g]}</td><td>{cell(cohorts.totals[g].persons, "persons")}</td><td>{cell(cohorts.totals[g].priced_out, "priced_out")}</td>
            <td>{cell(cohorts.totals[g].paid_milli, "paid_milli")} · {cell(cohorts.totals[g].refunded_milli, "refunded_milli")}</td>
            <td>{cell(cohorts.totals[g].credited_milli, "credited_milli")}</td><td>{cell(cohorts.totals[g].income_replaced, "income_replaced")}</td>
            <td>{cell(cohorts.totals[g].wages_milli, "wages_milli")}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="systems-note">Credited goes by the region of the claim sold; sellers provisioned in no pilot region are outside these groups. Crew wages are those of woodcutting, granary and repair crews (workshop firm wages are not attributed by person).</p>
        {cohorts.unknown.length > 0 ? <p className="systems-note">Not attributable exactly: {cohorts.unknown.map((u) => { const [rid, why] = u.split("|"); return `${region(Number(rid))} ${why}`; }).join("; ")}.</p> : null}
        {cohorts.states.malformed.length > 0 ? <p className="systems-note">Household groups rejected as malformed: {cohorts.states.malformed.join("; ")}.</p> : null}
      </>;
  const wars = readWarLosses(record, bundle.world_state.civilizations?.length ?? 0);
  const warThisTurn = wars.status === "ok" ? wars.losses.filter((w) => w.turn === record.source_turn) : [];
  const civ = (index: number | null, label: string | null) => label ?? (index === null ? "Unknown" : `Civilization ${index}`);
  // This turn's war events by the counter (the previous snapshot's record, when readable), against the
  // rows the rolling 64-record log still holds: a busy turn can push some of them out.
  const previous = (bundle.history ?? []).find((h) => h.turn === turn - 1) ?? null;
  const before = previous ? readHouseholdRetail(previous, regions.length) : null;
  const eventsThisTurn = wars.status === "ok" && before?.status === "ok" && rulesVersion(before.record) === 2
    ? c("war_events") - (before.record.counters.war_events ?? 0) : null;
  const truncated = wars.status === "ok" && (eventsThisTurn !== null ? eventsThisTurn > warThisTurn.length
    : record.log_dropped > 0 && record.log.length > 0 && record.log[0].turn === record.source_turn);
  const truncationNote = !truncated ? null : <p className="systems-note">{eventsThisTurn !== null
    ? `${plural(eventsThisTurn, "war event")} in pilot regions this turn; the rolling log (the last 64 records) kept ${plural(warThisTurn.length, "row")}, so the others' causes, actors and victims are not shown (not recorded here, not absent).`
    : "The rolling log (the last 64 records) dropped records of this turn, so this turn's war events may be more than shown."}</p>;
  const warSection = wars.status === "malformed"
    ? <p className="systems-note">The war losses of owned food were rejected as malformed: {wars.reason}.</p>
    : wars.status === "disabled"
      ? (thisTurn.some((e) => e.kind === "war_loss") ? <p className="systems-note">Rules version 1 records conquest losses of owned food without their cause, actor or victim (not recorded, unknown); sieges and occupations do not reach owned food there.</p> : null)
      : warThisTurn.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`War losses of owned food at snapshot ${turn}`}>
        <caption>War events in pilot regions this turn: each destroys the share of owned food it destroys of the commons, once{control ? " (the record-only control holds no food: each event is recorded with no loss)" : ""}.</caption>
        <thead><tr><th>Region</th><th>Cause</th><th>Actor</th><th>Victim (the region's ruler)</th><th>Owned food destroyed</th></tr></thead>
        <tbody>{warThisTurn.map((w, i) => <tr key={`${w.region}-${i}`}>
          <td>{link(w.region)}</td><td>{CAUSE_LABEL[w.cause]}</td><td>{civ(w.actor, w.actorName)} ({ACTOR_ROLE[w.cause]})</td>
          <td>{civ(w.victim, w.victimName)}</td><td>{w.milli ? food(w.milli) : control ? "none (nothing held)" : "none (no owned food)"}</td>
        </tr>)}</tbody>
      </table>{truncationNote}</div> : truncationNote;
  return <section className="systems-section" aria-label="Household retail">
    <h3>Household retail · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Mode: {RETAIL_MODE_LABEL[record.mode]}. Pilot boundary: {BOUNDARY_NOTE[record.boundary]}{scheduleNote}; {leaves}, and its owned food then returns to its commons. Title share θ = {number(theta)}: {number((1 - theta) * 100, 1)}% of each pilot harvest stays commons. The price is the market food price clamped to {number(p.price_floor)}–{number(p.price_cap)}, times the ration. At most {number(p.max_claims)} claims are held; a farmer or heir beyond that is refused and the share stays commons. Food in food units (two rations each), money in wealth units, deficits in rations. Retail rules version {v2 ? "2: each conquest, siege turn and occupation start reaches owned food once, recorded with its cause, actor and victim" : "1 (checkpoints 2–3): a conquest's share once per turn; sieges and occupations leave owned food alone"}.</p>
    {frames === null ? <p className="systems-note">The retail frame of simulation turn {record.source_turn} was not recorded: who ate, sold and paid, and who fell below their fair share, are unknown, not zero.</p>
      : frames.length === 0 ? <p className="systems-note">No region is in the pilot at simulation turn {record.source_turn}.</p> : <>
        {control ? <p className="systems-note">Nobody is provisioned by retail in this control; the food allocation section shows what people ate.</p> : <>
          <p className="systems-note">{riskSentence(record) ?? "No pilot region was provisioned this turn."}</p>
          {atRisk.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`People below their fair share at snapshot ${turn}`}>
            <caption>Children · persons · households below their fair share (deficit in rations), by cause: {causes.map((k) => RISK_LABEL[k]).join("; ")}.</caption>
            <thead><tr><th>Region (fair share)</th>{causes.map((k) => <th key={k}>{RISK_HEAD[k]}</th>)}</tr></thead>
            <tbody>{atRisk.map((r) => <tr key={r.region}>
              <td>{name(r)} ({number(r.provisioning!.fair_share)})</td>
              {causes.map((k) => <td key={k}>{riskCell(r.provisioning, k)}</td>)}
            </tr>)}</tbody>
          </table></div> : null}
          {sampled.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Sampled people below their fair share at snapshot ${turn}`}>
            <thead><tr><th>Person (household), region</th><th>Why</th><th>Ration of fair share</th></tr></thead>
            <tbody>{sampled.map(([id, rid, household, ration, fair, status]) => <tr key={`${rid}-${id}`}>
              <td>{id} ({household}), {link(rid)}</td><td>{STATUS_LABEL[RETAIL_STATUSES[status]]}</td>
              <td>{number(ration)} of {number(fair)}</td>
            </tr>)}</tbody>
          </table></div> : null}
          {sampled.length > 0 || record.sample_dropped ? <p className="systems-note">The person sample holds at most 24 people, those below their fair share first{record.sample_dropped ? `; ${record.sample_dropped} more were not sampled` : ""}. The region counts above are complete.</p> : null}
          {unprovisioned.length > 0 ? <p className="systems-note">Not provisioned by retail this turn (nothing installed there, or the tick took no install; its people were fed under the food allocation rule, in that section): {unprovisioned.map((r) => region(r.region)).join(", ")}.</p> : null}
          {cohortSection}
        </>}
        {control ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Would-be retail at snapshot ${turn}`}>
          <thead><tr><th>Region</th><th>Would-be title</th><th>Owners of farmers</th><th>Kept commons (no farmer)</th><th>Would-be price a ration</th><th>Merchants: commons out</th></tr></thead>
          <tbody>{frames.map((r) => <tr key={r.region}>
            <td>{name(r)}</td><td>{food(r.would_be?.titled_milli)}</td>
            <td>{r.would_be ? `${number(r.would_be.owners)} of ${number(r.would_be.farmers)}` : "Unknown"}</td>
            <td>{food(r.would_be?.untitled_milli)}</td>
            <td>{r.would_be?.price_milli === undefined ? "Unknown" : coins(r.would_be.price_milli)}</td>
            <td>{show(r.merchant_food_departing)}</td>
          </tr>)}</tbody>
        </table></div> : <>
          <div className="systems-table-wrap"><table className="systems-table" aria-label={`Owned food at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Owned: open → close (owners)</th><th>Titled (≈ commons share)</th>
              <th>Eaten · sold · unsold</th><th>Free food given</th><th>Decay · overflow</th>
              <th>To granaries · {v2 ? "war loss" : "conquest"}</th><th>To commons</th><th>Inherited</th></tr></thead>
            <tbody>{frames.map((r) => {
              const q = r.provisioning;
              const share = commonsShare(r, theta);
              const kept = commonsOf(r, "untitled") + commonsOf(r, "claims_refused");
              const why = COMMONS_REASONS.filter((k) => commonsOf(r, k) > 0).map((k) => `${COMMONS_LABEL[k]} ${food(commonsOf(r, k))}`);
              return <tr key={r.region}>
                <td>{name(r)}</td>
                <td>{food(r.open_milli)} → {food(r.close_milli)} ({r.owners})</td>
                <td>{food(ownedTitle(r))}{kept ? ` (+${food(kept)} titled but kept commons)` : ""} ({share === null ? "Unknown" : `≈${food(share)}`})</td>
                <td>{q ? `${food(flowOf(r, "own_eaten"))} · ${food(flowOf(r, "sold"))} · ${food(q.unsold_milli)}` : "not provisioned"}</td>
                <td>{q ? `${number(q.free_given)} of ${number(q.free_rations)}` : "not provisioned"}</td>
                <td>{food(flowOf(r, "decay"))} · {food(flowOf(r, "overflow"))}{flowOf(r, "cap_overflow") ? ` (+${food(flowOf(r, "cap_overflow"))} above the cap before granaries${capCut(r) ? `, with ${food(capCut(r)!.commons_milli)} of the commons` : ""})` : ""}</td>
                <td>{food(flowOf(r, "procured"))} · {food(flowOf(r, "war_loss"))}</td>
                <td>{why.length ? why.join("; ") : "none"}</td>
                <td>{food(flowOf(r, "inherited_in"))}</td>
              </tr>;
            })}</tbody>
          </table></div>
          <div className="systems-table-wrap"><table className="systems-table" aria-label={`Food money at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Price a ration</th><th>Paid · credited · refunded</th><th>Income replaced (farmers)</th>
              <th>Merchants: commons out · owned left (bound)</th></tr></thead>
            <tbody>{frames.map((r) => {
              const q = r.provisioning;
              return <tr key={r.region}>
                <td>{name(r)}</td><td>{priceCell(record, r)}</td>
                <td>{q ? `${coins(q.paid_milli)} · ${coins(q.credited_milli)} · ${coins(q.refunded_milli)}` : "not provisioned"}</td>
                <td>{incomeCell(record, r)}</td>
                <td>{r.merchant_food_departing === null ? "Unknown" : `${show(r.merchant_food_departing)} · at most ${food(r.owned_food_unloadable_milli)}`}</td>
              </tr>;
            })}</tbody>
          </table></div>
          <p className="systems-note">Titled: the owned share of this turn's harvest, with the part titled but kept commons (no farmer, or the claims cap); the commons share (1 − θ of the harvest) is derived from it. Eaten and sold are owners' claims debited; free food given is in rations, of the free rations installed (commons draw-down and granary release). Merchants: the food they committed from the commons, then the owned food they could not load. Merchants load only the commons, so that owned food is an upper bound on the departures foregone, not a measured loss.</p>
          {procurement ? <p className="systems-note">{record.mode === "free_exchange"
            ? `Granaries bought ${food((frames ?? []).reduce((a, r) => a + flowOf(r, "procured"), 0))} of owners' grain in ${procurement.procurement_flows} purchases; in this control nobody was paid (${coins(procurement.procurement_unpaid_milli)} stays with the treasury's old sink).`
            : `Granaries bought ${food((frames ?? []).reduce((a, r) => a + flowOf(r, "procured"), 0))} of owners' grain in ${procurement.procurement_flows} purchases; owners were credited ${coins(procurement.procurement_credited_milli)}${procurement.procurement_residual_milli ? ` (${coins(procurement.procurement_residual_milli)} refused by the wealth ceiling)` : ""}.`}</p> : null}
        </>}
      </>}
    {warSection}
    {thisTurn.length > 0 ? <p className="systems-note">Records this turn: {["pilot_opened", "pilot_closed", "war_loss", "inherited", "escheat", "pool_reset", "claims_refused", "switch_off"]
      .filter((k) => counts(k) > 0).map((k) => `${words(k)} ${counts(k)}`).join(", ")}.</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Household retail to snapshot ${turn}`}>
      <thead><tr><th>Lifetime</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Pilot region-turns · regions opened · closed</td><td>{number(c("pilot_region_turns"))} · {number(c("regions_opened"))} · {number(c("regions_closed"))}</td></tr>
        <tr><td>Turns settled · installs not taken · unobserved</td><td>{number(c("turns_settled"))} · {number(c("turns_not_taken"))} · {number(c("turns_unobserved"))}</td></tr>
        <tr><td>Titled to owners (titled but kept commons)</td><td>{food(c("titled_milli"))} ({food(c("untitled_milli"))})</td></tr>
        <tr><td>Own food eaten · sold to neighbours · sold to granaries</td><td>{food(c("own_eaten_milli"))} · {food(c("sold_milli"))} · {food(c("procured_milli"))}</td></tr>
        {v2 ? <>
          <tr><td>Decay · storage overflow</td><td>{food(c("decay_milli"))} · {food(c("overflow_milli"))}</td></tr>
          <tr><td>War loss: conquest · siege · occupation (war events)</td><td>{WAR_CAUSES.map((k) => food(c(`war_loss_${k}_milli`))).join(" · ")} ({number(c("war_events"))})</td></tr>
        </> : <tr><td>Decay · storage overflow · conquest loss</td><td>{food(c("decay_milli"))} · {food(c("overflow_milli"))} · {food(c("war_loss_milli"))}</td></tr>}
        <tr><td>To commons (of it, no heir)</td><td>{food(c("to_commons_milli"))} ({food(c("escheat_milli"))})</td></tr>
        <tr><td>Inherited · owners who died</td><td>{food(c("inherited_milli"))} · {number(c("deaths"))}</td></tr>
        <tr><td>Paid · credited · refunded</td><td>{coins(c("paid_milli"))} · {coins(c("credited_milli"))} · {coins(c("refunded_milli"))}</td></tr>
        <tr><td>Granary purchases: credited · refused by the ceiling · unpaid</td><td>{coins(c("procurement_credited_milli"))} · {coins(c("procurement_residual_milli"))} · {coins(c("procurement_unpaid_milli"))}</td></tr>
        <tr><td>Farm income replaced (farmer-turns)</td><td>{number(record.income_replaced_total)} ({number(c("income_replaced_rows"))})</td></tr>
        <tr><td>Person-turns priced out · offer short</td><td>{number(c("priced_out_persons"))} · {number(c("offer_short_persons"))}</td></tr>
        <tr><td>Claims refused (cap) · region-turns exempt from requisition</td><td>{number(c("claims_refused"))} · {v2 ? "not applicable (rules version 2 applies sieges and occupations to owned food)" : number(c("requisition_exempt_region_turns"))}</td></tr>
        {v2 ? <tr><td>Grain above the storage cap, lost before granaries buy: owned · commons</td><td>{aboveCap}</td></tr> : null}
        <tr><td>Crew farm time paid as wages, not titled (person-turns)</td><td>{number(c("crew_farm_time_person_turns"))}</td></tr>
      </tbody>
    </table></div>
    {notable.length > 0 ? <p className="systems-note">Recent pilot records: {notable.map((e) =>
      `turn ${e.turn} ${region(e.region)} ${words(e.kind)}${e.milli ? ` ${food(e.milli)}` : ""}${e.note ? ` (${e.note})` : ""}`).join("; ")}.</p> : null}
    {record.log_dropped ? <p className="systems-note">{record.log_dropped} older records were dropped from the rolling log.</p> : null}
  </section>;
}
