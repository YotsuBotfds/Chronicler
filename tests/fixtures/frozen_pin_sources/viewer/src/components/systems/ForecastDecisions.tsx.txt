import { useState } from "react";
import type { Bundle, Event, TurnSnapshot } from "../../types";
import { forecastDecisionsAt } from "../../lib/forecastDecision";

const PAGE = 8;
const show = (n: number | null) => n === null ? "Not observed" : n === 0 ? "0" : n < .001 ? n.toExponential(3) : n.toLocaleString(undefined, { maximumFractionDigits: 3 });
const percent = (n: number) => `${show(n * 100)}%`;

/** Only reports captured by the procurement decider; no inferred attempts. */
export function ForecastDecisions({ bundle, snapshot, currentTurn, onSelectRegion, onSelectCivilization, onSelectEvent }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
  onSelectCivilization: (name: string) => void; onSelectEvent: (event: Event) => void;
}) {
  const at = snapshot?.turn ?? currentTurn;
  const [page, setPage] = useState({ turn: at, limit: PAGE });
  if (page.turn !== at) setPage({ turn: at, limit: PAGE });
  const limit = page.turn === at ? page.limit : PAGE;
  const regions = bundle.world_state.regions ?? [], civs = bundle.world_state.civilizations ?? [];
  const frame = forecastDecisionsAt(snapshot?.turn === currentTurn ? snapshot : null, regions.length, civs.length);
  if (!frame) return <section className="systems-stack" aria-label="Forecast procurement decisions">
    <h4>Forecast procurement decisions</h4><p className="systems-note">Decision-boundary evidence is not observed or unavailable at this snapshot.</p>
  </section>;
  const event = (id: string, kind: string, turn: number) => id ? (bundle.events_timeline ?? []).find(
    (e) => e.event_id === id && e.event_type === kind && e.turn === turn && e.turn <= frame.source_turn) : undefined;
  return <section className="systems-stack" style={{ overflowWrap: "anywhere" }} aria-label="Forecast procurement decisions">
    <h4>Forecast procurement decisions · snapshot {at}</h4>
    <p className="systems-note">Actual Phase 10 procurement boundary in simulation turn {frame.source_turn}; mode {frame.mode}. Amounts are model food goods and model treasury coins. These are observed decisions and flows, not estimates of extra purchases caused by a warning.</p>
    <p className="systems-note">Each listed report was received and eligible at this boundary; the list does not establish every report a recipient may have received. An empty list does not establish an unsuccessful purchase attempt.</p>
    {frame.rows.length === 0 ? <p className="systems-note">A decision frame was recorded with no granary rows.</p> : <>
      <p>Showing {Math.min(limit, frame.rows.length)} of {frame.rows.length} recorded granary decisions.</p>
      {frame.rows.slice(0, limit).map((row) => { const d = row.decision; return <article key={d.region}>
        <h4><button type="button" className="systems-link" onClick={() => onSelectRegion(regions[d.region].name)}>{regions[d.region].name}</button></h4>
        <p>Granary keeper: <button type="button" className="systems-link" onClick={() => onSelectCivilization(civs[d.owner].name)}>{civs[d.owner].name}</button> · Territorial controller: {d.controller === null ? "Uncontrolled or not recorded" : <button type="button" className="systems-link" onClick={() => onSelectCivilization(civs[d.controller!].name)}>{civs[d.controller].name}</button>}.</p>
        <p>Target before: {show(d.target_before)} · Requested target: {show(d.requested_target)} · Feasible target: {show(d.feasible_target)}.</p>
        <p>Granary stock: {show(d.granary_stock)} · Food demand: {show(d.food_demand)} · Pending inbound: {show(d.pending_inbound)} · Opening budget: {show(d.opening_budget)}.</p>
        <p>New purchase received: {show(row.purchased_grain)} · New paid cargo committed: {show(row.committed_grain)} · Treasury paid: {show(row.paid)}. Unsuccessful attempts are not observed.</p>
        {d.reports.length === 0 ? <p>No eligible warning report was recorded in this decision.</p> : <ul>{d.reports.map((r) => <li key={r.id}>
          <p>Report {r.id} from {regions[r.source_region].name}: issued turn {r.issued_turn}, planned delivery {r.planned_delivery_turn}, received {r.delivered_turn}, expires {r.expires_turn}; target window {r.target_start}–{r.target_end}.</p>
          <p>Original shortfall risk {percent(r.probability)} · confidence {percent(r.confidence)} · predicted production ÷ demand {show(r.predicted_ratio)}.</p>
          {([r.issued_event_id, r.delivered_event_id] as const).map((id, i) => { const found = event(id, i === 0 ? "harvest_forecast_issued" : "harvest_forecast_delivered", i === 0 ? r.issued_turn : r.delivered_turn); return found ? <button key={id} type="button" className="systems-link" onClick={() => onSelectEvent(found)}>{i === 0 ? "Inspect issue event" : "Inspect delivery event"}</button> : null; })}
        </li>)}</ul>}
      </article>; })}
      {limit < frame.rows.length && <button type="button" className="phase75-ghost-button" onClick={() => setPage({ turn: at, limit: limit + PAGE })}>Show more granary decisions ({frame.rows.length - limit} remaining)</button>}
    </>}
  </section>;
}
