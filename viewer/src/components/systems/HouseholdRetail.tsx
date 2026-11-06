import type { Bundle, TurnSnapshot } from "../../types";
import {
  COMMONS_REASONS, RETAIL_MODE_LABEL, RETAIL_STATUSES, RISKS, commonsOf, commonsShare, flowOf, ownedTitle, readHouseholdRetail, riskTotals,
  type HouseholdRetailRecord, type RetailRegionFrame, type Risk,
} from "../../lib/householdRetail";

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
};
const RISK_LABEL: Record<Risk, string> = {
  priced_out: "Priced out (cash ran out)",
  offer_short: "Offer short (not enough food on offer)",
  withheld_dead: "Withheld (a dead owner's claim held for the heirs)",
};
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
  const head = `${persons} people (${children} children) were provisioned in ${provisioned.length} pilot region${provisioned.length === 1 ? "" : "s"}.`;
  const below = RISKS.filter((k) => totals[k].persons > 0);
  if (!below.length) return `${head} Everyone reached their fair share.`;
  return `${head} Below their fair share: ${below.map((k) => `${words(k)} ${totals[k].children} children of ${totals[k].persons} people in ${totals[k].households} households, deficit ${number(totals[k].deficit)} rations`).join("; ")}.`;
}

function incomeCell(record: HouseholdRetailRecord, r: RetailRegionFrame): string {
  if (record.mode === "free_exchange") return "kept (not replaced)";
  if (record.mode === "record_only") return "not replaced";
  if (r.income_replaced !== null) return `${number(r.income_replaced)} (${r.income_rows} farmers)`;
  return r.provisioning !== null && record.income && Object.keys(record.income).length ? "none (no farmer rows)" : "Unknown";
}

function priceCell(record: HouseholdRetailRecord, r: RetailRegionFrame): string {
  if (r.price_milli === null) return "Unknown";
  if (record.mode === "free_exchange") return "not charged";
  return `${coins(r.price_milli)} a ration`;
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
  const sampled = (record.sample ?? []).filter((s) => s[5] !== 0);
  const money = record.money ?? {};
  const procurement = "procurement_flows" in money ? money : null;
  const counts = (kind: string) => thisTurn.filter((e) => e.kind === kind).length;
  const notable = record.log.filter((e) => !["inherited", "escheat"].includes(e.kind)).slice(-8);
  const theta = p.theta;
  return <section className="systems-section" aria-label="Household retail">
    <h3>Household retail · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Mode: {RETAIL_MODE_LABEL[record.mode]}. Pilot boundary: {BOUNDARY_NOTE[record.boundary]}; a region leaves only when it has no controller, and its owned food then returns to its commons. Title share θ = {number(theta)}: {number((1 - theta) * 100, 1)}% of each pilot harvest stays commons. The price is the market food price clamped to {number(p.price_floor)}–{number(p.price_cap)}, times the ration. At most {number(p.max_claims)} claims are held; a farmer or heir beyond that is refused and the share stays commons. Food in food units (two rations each), money in wealth units, deficits in rations.</p>
    {frames === null ? <p className="systems-note">The retail frame of simulation turn {record.source_turn} was not recorded: who ate, sold and paid, and who fell below their fair share, are unknown, not zero.</p>
      : frames.length === 0 ? <p className="systems-note">No region is in the pilot at simulation turn {record.source_turn}.</p> : <>
        {control ? <p className="systems-note">Nobody is provisioned by retail in this control; the food allocation section shows what people ate.</p> : <>
          <p className="systems-note">{riskSentence(record) ?? "No pilot region was provisioned this turn."}</p>
          {atRisk.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`People below their fair share at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Fair share (regional sufficiency)</th>
              {RISKS.map((k) => <th key={k}>{RISK_LABEL[k]}: children · persons · households (deficit)</th>)}</tr></thead>
            <tbody>{atRisk.map((r) => <tr key={r.region}>
              <td>{name(r)}</td><td>{number(r.provisioning!.fair_share)} ({number(r.provisioning!.sufficiency)})</td>
              {RISKS.map((k) => <td key={k}>{riskCell(r.provisioning, k)}</td>)}
            </tr>)}</tbody>
          </table></div> : null}
          {sampled.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Sampled people below their fair share at snapshot ${turn}`}>
            <thead><tr><th>Person</th><th>Region</th><th>Household</th><th>Ration of fair share</th><th>Why</th></tr></thead>
            <tbody>{sampled.map(([id, rid, household, ration, fair, status]) => <tr key={`${rid}-${id}`}>
              <td>{id}</td><td>{link(rid)}</td><td>{household}</td><td>{number(ration)} of {number(fair)}</td>
              <td>{STATUS_LABEL[RETAIL_STATUSES[status]]}</td>
            </tr>)}</tbody>
          </table></div> : null}
          {sampled.length > 0 || record.sample_dropped ? <p className="systems-note">The person sample holds at most 24 people, those below their fair share first{record.sample_dropped ? `; ${record.sample_dropped} more were not sampled` : ""}. The region counts above are complete.</p> : null}
          {unprovisioned.length > 0 ? <p className="systems-note">Not provisioned this turn (eating, sales, payments and people below their fair share unknown, not zero): {unprovisioned.map((r) => region(r.region)).join(", ")}.</p> : null}
        </>}
        {control ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Would-be retail at snapshot ${turn}`}>
          <thead><tr><th>Region</th><th>Would-be title</th><th>Owners of farmers</th><th>Would stay commons (no farmer)</th><th>Would-be price</th><th>Merchant food departing</th></tr></thead>
          <tbody>{frames.map((r) => <tr key={r.region}>
            <td>{name(r)}</td><td>{food(r.would_be?.titled_milli)}</td>
            <td>{r.would_be ? `${number(r.would_be.owners)} of ${number(r.would_be.farmers)}` : "Unknown"}</td>
            <td>{food(r.would_be?.untitled_milli)}</td>
            <td>{r.would_be?.price_milli === undefined ? "Unknown" : `${coins(r.would_be.price_milli)} a ration`}</td>
            <td>{show(r.merchant_food_departing)}</td>
          </tr>)}</tbody>
        </table></div> : <>
          <div className="systems-table-wrap"><table className="systems-table" aria-label={`Owned food at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Owned open → close (owners)</th><th>Titled to owners (commons share)</th>
              <th>Own food eaten · sold · unsold</th><th>Free food given (of free rations)</th><th>Decay · overflow</th>
              <th>Sold to granaries · conquest loss</th><th>To commons (why)</th><th>Inherited</th></tr></thead>
            <tbody>{frames.map((r) => {
              const q = r.provisioning;
              const share = commonsShare(r, theta);
              const kept = commonsOf(r, "untitled") + commonsOf(r, "claims_refused");
              const why = COMMONS_REASONS.filter((k) => commonsOf(r, k) > 0).map((k) => `${COMMONS_LABEL[k]} ${food(commonsOf(r, k))}`);
              return <tr key={r.region}>
                <td>{name(r)}</td>
                <td>{food(r.open_milli)} → {food(r.close_milli)} ({r.owners})</td>
                <td>{food(ownedTitle(r))}{kept ? ` (+${food(kept)} titled but kept commons)` : ""} ({share === null ? "Unknown" : `≈${food(share)}`})</td>
                <td>{food(flowOf(r, "own_eaten"))} · {food(flowOf(r, "sold"))} · {q ? food(q.unsold_milli) : "Unknown"}</td>
                <td>{q ? `${number(q.free_given)} of ${number(q.free_rations)}` : r.free_rations === null ? "Unknown" : `Unknown of ${number(r.free_rations)}`}</td>
                <td>{food(flowOf(r, "decay"))} · {food(flowOf(r, "overflow"))}</td>
                <td>{food(flowOf(r, "procured"))} · {food(flowOf(r, "war_loss"))}</td>
                <td>{why.length ? why.join("; ") : "none"}</td>
                <td>{food(flowOf(r, "inherited_in"))}</td>
              </tr>;
            })}</tbody>
          </table></div>
          <div className="systems-table-wrap"><table className="systems-table" aria-label={`Food money at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Price</th><th>Paid · credited · refunded</th><th>Farm income replaced (farmers)</th>
              <th>Merchant food departing from the commons · owned food merchants could not load (foregone departures at most)</th></tr></thead>
            <tbody>{frames.map((r) => {
              const q = r.provisioning;
              return <tr key={r.region}>
                <td>{name(r)}</td><td>{priceCell(record, r)}</td>
                <td>{q ? `${coins(q.paid_milli)} · ${coins(q.credited_milli)} · ${coins(q.refunded_milli)}` : "Unknown"}</td>
                <td>{incomeCell(record, r)}</td>
                <td>{r.merchant_food_departing === null ? "Unknown" : `${show(r.merchant_food_departing)} · at most ${food(r.owned_food_unloadable_milli)}`}</td>
              </tr>;
            })}</tbody>
          </table></div>
          <p className="systems-note">Commons share: the part of each pilot harvest that stays commons (1 − θ), derived from the title. Merchants load only the commons: the owned food they could not load bounds the departures foregone; it is not a measured loss.</p>
          {procurement ? <p className="systems-note">{record.mode === "free_exchange"
            ? `Granaries bought ${food((frames ?? []).reduce((a, r) => a + flowOf(r, "procured"), 0))} of owners' grain in ${procurement.procurement_flows} purchases; in this control nobody was paid (${coins(procurement.procurement_unpaid_milli)} stays with the treasury's old sink).`
            : `Granaries bought ${food((frames ?? []).reduce((a, r) => a + flowOf(r, "procured"), 0))} of owners' grain in ${procurement.procurement_flows} purchases; owners were credited ${coins(procurement.procurement_credited_milli)}${procurement.procurement_residual_milli ? ` (${coins(procurement.procurement_residual_milli)} refused by the wealth ceiling)` : ""}.`}</p> : null}
        </>}
      </>}
    {thisTurn.length > 0 ? <p className="systems-note">Records this turn: {["pilot_opened", "pilot_closed", "war_loss", "inherited", "escheat", "pool_reset", "claims_refused", "switch_off"]
      .filter((k) => counts(k) > 0).map((k) => `${words(k)} ${counts(k)}`).join(", ")}.</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Household retail to snapshot ${turn}`}>
      <thead><tr><th>Lifetime</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Pilot region-turns · regions opened · closed</td><td>{c("pilot_region_turns")} · {c("regions_opened")} · {c("regions_closed")}</td></tr>
        <tr><td>Turns settled · installs not taken · unobserved</td><td>{c("turns_settled")} · {c("turns_not_taken")} · {c("turns_unobserved")}</td></tr>
        <tr><td>Titled to owners (titled but kept commons)</td><td>{food(c("titled_milli"))} ({food(c("untitled_milli"))})</td></tr>
        <tr><td>Own food eaten · sold to neighbours · sold to granaries</td><td>{food(c("own_eaten_milli"))} · {food(c("sold_milli"))} · {food(c("procured_milli"))}</td></tr>
        <tr><td>Decay · storage overflow · conquest loss</td><td>{food(c("decay_milli"))} · {food(c("overflow_milli"))} · {food(c("war_loss_milli"))}</td></tr>
        <tr><td>To commons (of it, no heir)</td><td>{food(c("to_commons_milli"))} ({food(c("escheat_milli"))})</td></tr>
        <tr><td>Inherited · owners who died</td><td>{food(c("inherited_milli"))} · {c("deaths")}</td></tr>
        <tr><td>Paid · credited · refunded</td><td>{coins(c("paid_milli"))} · {coins(c("credited_milli"))} · {coins(c("refunded_milli"))}</td></tr>
        <tr><td>Granary purchases: credited · refused by the ceiling · unpaid</td><td>{coins(c("procurement_credited_milli"))} · {coins(c("procurement_residual_milli"))} · {coins(c("procurement_unpaid_milli"))}</td></tr>
        <tr><td>Farm income replaced (farmer-turns)</td><td>{number(record.income_replaced_total)} ({c("income_replaced_rows")})</td></tr>
        <tr><td>Person-turns priced out · offer short</td><td>{c("priced_out_persons")} · {c("offer_short_persons")}</td></tr>
        <tr><td>Claims refused (cap) · region-turns exempt from requisition</td><td>{c("claims_refused")} · {c("requisition_exempt_region_turns")}</td></tr>
        <tr><td>Crew farm time paid as wages, not titled (person-turns)</td><td>{c("crew_farm_time_person_turns")}</td></tr>
      </tbody>
    </table></div>
    {notable.length > 0 ? <p className="systems-note">Recent pilot records: {notable.map((e) =>
      `turn ${e.turn} ${region(e.region)} ${words(e.kind)}${e.milli ? ` ${food(e.milli)}` : ""}${e.note ? ` (${e.note})` : ""}`).join("; ")}.</p> : null}
    {record.log_dropped ? <p className="systems-note">{record.log_dropped} older records were dropped from the rolling log.</p> : null}
  </section>;
}
