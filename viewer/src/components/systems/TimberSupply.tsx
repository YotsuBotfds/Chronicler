import type { Bundle, TurnSnapshot } from "../../types";
import {
  lossCounts, readTimberSupply, refusalCounts, type ExpeditionReceiptRecord, type ExpeditionRecord, type TimberNeedRecord,
} from "../../lib/timberSupply";
import { show, words } from "./formatters";

const coins = (milli: number) => (milli / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const REFUSAL: Record<string, string> = {
  no_forest: "no forest the ruler or nobody controls is reachable",
  too_far: "no forest within the hop limit",
  forest_depleted: "every forest in range is below the stock guard",
  forest_busy: "every healthy forest in range is already being cut",
  no_crew: "nobody at home is eligible",
  no_coins: "the treasury cannot pay the whole expedition",
};
const END: Record<string, string> = {
  crew_lost: "crew lost", no_coins: "treasury short", home_lost: "home region lost", forest_lost: "forest lost",
  pool_reset: "native pool rebuilt", switched_off: "switched off",
};
const MODE_NOTE: Record<string, string> = {
  supply: "Supply: a region with open repairs and a timber gap sends a named crew to cut the nearest healthy forest and carry the timber home to a store reserved for its repairs.",
  cost_only: "Cost-only control: the same expeditions, crews, travel, reservations, wages and farm labour taken from home, but nobody cuts. No timber is cut, no forest stock is debited and nothing is delivered. It matches the cost of one expedition, not the run's total: its need is never met, so it keeps launching.",
};

function stockText(r: ExpeditionReceiptRecord): string {
  if (r.stock_before === null || r.stock_after === null) return r.stage === "cutting" ? "Unknown" : "—";
  return `${show(r.stock_before, 1)} → ${show(r.stock_after, 1)} of ${show(r.capacity, 1)}`;
}

function flags(r: ExpeditionReceiptRecord): string {
  const out = [];
  if (r.unpaid) out.push("walked home unpaid");
  if (r.recalled) out.push("recalled (treasury could not pay)");
  if (r.cut_end) out.push(`cutting ended: ${words(r.cut_end)}`);
  if (r.dropped.length) out.push(`left the crew: ${r.dropped.map(([id, why]) => `${id} (${words(why)})`).join(", ")}`);
  return out.join("; ") || "—";
}

function ended(e: ExpeditionRecord): string {
  if (e.status === "delivered") return `delivered ${show(e.delivered)} of ${show(e.cut)} cut`;
  if (e.status === "returned") return "came home with nothing to deliver";
  const where = e.end_reason === "home_lost" ? "left at home as commons" : "left at the forest as commons";
  return `${END[e.end_reason ?? ""] ?? words(e.end_reason)}, ${show(e.abandoned)} ${where}`;
}

function needText(n: TimberNeedRecord): string {
  if (n.status === "refused") return `Refused: ${REFUSAL[n.reason ?? ""] ?? words(n.reason)}`;
  if (n.status === "launched") return `Launched expedition #${n.eid}`;
  if (n.status === "expedition") return `Expedition #${n.eid} under way`;
  return "Supplied (gap below the launch minimum)";
}

/** Completed-turn timber supply only; never reads final-world state. */
export function TimberSupply({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readTimberSupply(snapshot, regions.length, civs.length);
  const at = snapshot?.turn ?? currentTurn;
  if (reading.status !== "ok") return <section className="systems-section" aria-label="Timber supply">
    <h3>Timber supply</h3>
    <p className="systems-note">{reading.status === "absent"
      ? `Timber supply is not observed at snapshot ${at}.`
      : `The timber supply record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
  </section>;
  const record = reading.record;
  const turn = record.source_turn + 1;
  const p = record.parameters;
  const c = (key: string) => record.counters[key] ?? 0;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const civ = (index: number) => civs[index]?.name ?? `Civ ${index}`;
  const link = (index: number) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(region(index))}>{region(index)}</button>;
  const route = (e: { home: number; forest: number }) => e.home === e.forest ? <>{link(e.home)} (home forest)</> : <>{link(e.home)} → {link(e.forest)}</>;
  const refusals = refusalCounts(record);
  const losses = lossCounts(record);
  const needs = record.needs ?? [];
  const acted = needs.filter((n) => n.status !== "supplied");
  const per = record.per_expedition;
  const control = record.mode === "cost_only";
  return <section className="systems-section" aria-label="Timber supply">
    <h3>Timber supply · snapshot {turn}</h3>
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Crews of at most {show(p.crew_cap)} adults stay residents of their home region: each turn away they are reserved for the whole turn, paid {coins(p.wage_milli)} a person-turn from the ruler&apos;s treasury in place of their ordinary income, and their farm labour leaves the home land. A trip takes one turn a hop each way (at most {show(p.max_hops)} hops) and {show(p.cut_turns)} turns of cutting; cutting stops below {show(p.guard_share)} of the forest&apos;s capacity. The harvest is debited from the forest&apos;s timber stock; {show(p.transit_decay * 100)}% a hop decays on the way home. Cargo of a crew lost on the way is left at the forest as commons (at home if home changed hands), never destroyed.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Timber supply accounts to snapshot ${turn}`}>
      <thead><tr><th>Lifetime</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Expeditions launched (veterans aboard)</td><td>{show(c("launched") + c("launched_works"))} ({show(c("launched_veterans"))}){c("launched_works") > 0 ? `; ${show(c("launched_works"))} of them for infrastructure works' timber, after every repair-project need` : ""}</td></tr>
        <tr><td>Expeditions delivered · came home empty · ended without delivering</td><td>{show(c("delivered_expeditions"))} · {show(c("returned_expeditions"))} · {show(c("ended") - c("delivered_expeditions") - c("returned_expeditions"))}</td></tr>
        <tr><td>Timber cut (debited from forest stocks)</td><td>{show(c("cut"))}</td></tr>
        <tr><td>Delivered to repair stores</td><td>{show(c("delivered"))}</td></tr>
        <tr><td>Lost to transit decay</td><td>{show(c("lost"))}</td></tr>
        <tr><td>Abandoned as commons (at the forest, or at home if it changed hands)</td><td>{show(c("abandoned_cargo"))}</td></tr>
        <tr><td>Released from stores to stockpiles (no open repair)</td><td>{show(c("released"))}</td></tr>
        <tr><td>Used by repairs from stores (held − returned)</td><td>{show(c("store_held") - c("store_returned"))}</td></tr>
        <tr><td>Wages paid (refused by the wealth ceiling)</td><td>{coins(c("wages_milli"))} ({coins(c("wage_residual_milli"))})</td></tr>
        <tr><td>Treasury charged (whole units)</td><td>{show(c("charged"))}</td></tr>
        <tr><td>Ordinary income withheld from the crews</td><td>{show(c("income_withheld"))}</td></tr>
        <tr><td>Farm labour away from home (removed of asked, headcount-turns)</td><td>{show(c("away_delivered"))} of {show(c("away_requested"))}</td></tr>
        <tr><td>Crew person-turns: outbound · cutting · returning</td><td>{show(c("crew_turns_outbound"))} · {show(c("crew_turns_cutting"))} · {show(c("crew_turns_returning"))}</td></tr>
        <tr><td>Recalls · return turns walked unpaid</td><td>{show(c("recalls"))} · {show(c("unpaid_turns"))}</td></tr>
      </tbody>
    </table></div>
    {per === null ? <p className="systems-note">No expedition has ended yet; per-expedition costs are unknown.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Per ended expedition to snapshot ${turn}`}>
        <thead><tr><th>Ended</th><th>Wages</th><th>Person-turns</th><th>Farm labour away</th><th>Unpaid turns</th><th>Cut</th><th>Delivered</th></tr></thead>
        <tbody><tr><td>{show(per.ended)}</td><td>{coins(per.wages_milli)}</td><td>{show(per.person_turns, 2)}</td><td>{show(per.farm_labor_away, 2)}</td>
          <td>{show(per.unpaid_turns, 2)}</td><td>{show(per.cut)}</td><td>{show(per.delivered)}</td></tr></tbody>
      </table></div>}
    {per !== null ? <p className="systems-note">Means over ended expeditions{control ? ": the comparison the cost-only control supports (it matches one expedition's cost, not the total)" : ""}.</p> : null}
    <p className="systems-note">Refused launches (lifetime): {refusals.length ? refusals.map(([k, v]) => `${REFUSAL[k] ?? words(k)} ${v}`).join("; ") : "none"}. Ended without delivering: {losses.abandoned.length ? losses.abandoned.map(([k, v]) => `${END[k] ?? words(k)} ${v}`).join(", ") : "none"}. Crew members who left: {losses.dropped.length ? losses.dropped.map(([k, v]) => `${words(k)} ${v}`).join(", ") : "none"}.</p>
    {record.receipts === null || record.ledger === null
      ? <p className="systems-note">No completed Phase 2 was recorded in simulation turn {record.source_turn}; this turn&apos;s crews, wages, farm labour and harvest are unknown, not zero.</p>
      : record.receipts.length === 0 ? <p className="systems-note">No expedition worked this turn.</p> : <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Expeditions this turn at snapshot ${turn}`}>
          <thead><tr><th>Expedition</th><th>Route</th><th>Stage</th><th>Crew</th><th>Farm labour away (removed of asked)</th><th>On the forest · cut</th><th>Forest stock (L3)</th><th>Wages · income withheld</th><th>Notes</th></tr></thead>
          <tbody>{record.receipts.map((r) => <tr key={r.eid}>
            <td>#{r.eid} ({civ(r.civ)})</td><td>{route(r)}</td><td>{r.stage}</td>
            <td>{r.crew.length ? r.crew.map((id) => r.veterans.includes(id) ? `${id} (veteran)` : `${id}`).join(", ") : "nobody"}</td>
            <td>{show(r.away_delivered)} of {show(r.away_requested)}</td>
            <td>{show(r.crew_labor)} · {show(r.cut)} (cargo {show(r.cargo_after)})</td>
            <td>{stockText(r)}</td>
            <td>{r.unpaid ? "unpaid" : `${coins(r.wages_milli)}${r.wage_residual_milli ? ` (+${coins(r.wage_residual_milli)} refused)` : ""}`} · {show(r.income_withheld)}</td>
            <td>{flags(r)}</td>
          </tr>)}</tbody>
        </table></div>
        {record.ledger.length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Expedition wages at snapshot ${turn}`}>
          <thead><tr><th>Ruler</th><th>Expeditions</th><th>Person-turns</th><th>Wages</th><th>Charged (whole units, prepaid remainder)</th></tr></thead>
          <tbody>{record.ledger.map((l) => <tr key={l.civ}>
            <td>{civ(l.civ)}</td><td>{l.expeditions}</td><td>{l.person_turns}</td>
            <td>{coins(l.wages_applied_milli)}{l.wage_residual_milli ? ` (+${coins(l.wage_residual_milli)} refused)` : ""}</td>
            <td>{`${l.charged} (prepaid ${coins(l.prepaid_before_milli)} → ${coins(l.prepaid_after_milli)})`}</td>
          </tr>)}</tbody>
        </table></div> : <p className="systems-note">Every expedition walked unpaid this turn: nothing was charged.</p>}
      </>}
    {record.expeditions.length === 0 ? <p className="systems-note">No expedition is under way.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Live expeditions at snapshot ${turn}`}>
        <thead><tr><th>Expedition</th><th>Route (hops)</th><th>Stage</th><th>Crew now / launched</th><th>Cargo · cut</th><th>Wages so far</th><th>Farm labour away so far</th><th>Unpaid turns</th></tr></thead>
        <tbody>{record.expeditions.map((e: ExpeditionRecord) => <tr key={e.eid}>
          <td>#{e.eid} ({civ(e.civ)}, launched turn {e.launched_turn})</td><td>{route(e)} ({e.hops})</td>
          <td>{e.stage}{e.recalled_turn !== null ? ` (recalled turn ${e.recalled_turn})` : ""}</td>
          <td>{e.crew.length} / {e.launched_crew.length}</td><td>{show(e.cargo)} · {show(e.cut)}</td>
          <td>{coins(e.wages_milli)}</td><td>{show(e.away_delivered)}</td><td>{e.unpaid_turns}</td>
        </tr>)}</tbody>
      </table></div>}
    {record.needs === null ? <p className="systems-note">The timber needs of simulation turn {record.source_turn} were not recorded; needs, stores and deposits are unknown, not zero.</p> : <>
      {acted.length === 0 ? <p className="systems-note">{needs.length ? `All ${needs.length} regions with open repairs had their timber (no gap worth an expedition).` : "No region has open repairs needing timber."}</p> :
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Timber needs at snapshot ${turn}`}>
          <thead><tr><th>Region</th><th>Ruler</th><th>Repairs could use</th><th>Free (of it in store)</th><th>In transit</th><th>Gap</th><th>Outcome</th></tr></thead>
          <tbody>{acted.map((n) => <tr key={n.region}>
            <td>{link(n.region)}</td><td>{civ(n.civ)}</td><td>{show(n.want)}</td><td>{show(n.free)} ({show(n.store)})</td>
            <td>{show(n.in_transit)}</td><td>{show(n.gap)}</td><td>{needText(n)}</td>
          </tr>)}</tbody>
        </table></div>}
      {acted.length > 0 && needs.length > acted.length ? <p className="systems-note">{needs.length - acted.length} more regions with open repairs had their timber.</p> : null}
      {record.needs_dropped ? <p className="systems-note">{record.needs_dropped} need rows beyond the bound were not recorded.</p> : null}
      {(record.stores ?? []).length > 0 ? <div className="systems-table-wrap"><table className="systems-table" aria-label={`Timber stores at snapshot ${turn}`}>
        <thead><tr><th>Region</th><th>Opening</th><th>Held by repairs</th><th>Returned unused</th><th>Delivered</th><th>Released to stockpile</th><th>Closing</th></tr></thead>
        <tbody>{(record.stores ?? []).map((s) => <tr key={s.region}>
          <td>{link(s.region)}</td><td>{show(s.opening)}</td><td>{show(s.held)}</td><td>{show(s.returned)}</td>
          <td>{show(s.delivered)}</td><td>{show(s.released)}</td><td>{show(s.closing)}</td>
        </tr>)}</tbody>
      </table></div> : <p className="systems-note">No region holds timber reserved for repairs.</p>}
      {(record.deposits ?? []).length > 0 ? <p className="systems-note">Cargo left as commons this turn: {(record.deposits ?? []).map(([, eid, rid, amount]) =>
        `${show(amount)} from expedition #${eid} in ${region(rid)}`).join("; ")}.</p> : null}
    </>}
    {record.closed.length > 0 ? <p className="systems-note">Recently ended: {record.closed.slice(-8).map((e) =>
      `#${e.eid} ${region(e.home)} (${ended(e)}, turn ${e.ended_turn}, wages ${coins(e.wages_milli)})`).join("; ")}.</p> : null}
  </section>;
}
