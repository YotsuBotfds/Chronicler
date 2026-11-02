import { useState } from "react";
import type { Bundle, SeatRecord, TurnSnapshot } from "../../types";
import { learningServicesAt } from "../../lib/learningServices";
import { exactSnapshot } from "../../lib/historyComparison";

const PAGE = 8;
const value = (v: number | null | undefined) => v == null ? "Not observed" : v === 0 ? "0"
  : Math.abs(v) < .001 ? v.toExponential(3) : v.toLocaleString(undefined, { maximumFractionDigits: 3 });
const yes = (v: boolean | null) => v === null ? "Not observed" : v ? "Yes" : "No";

export function AcademyServices({ bundle, snapshot, seatId, seat, currentTurn, onSeek, onSelectRegion, onSelectCivilization }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; seatId: number; seat: SeatRecord | null; currentTurn: number;
  onSeek: (turn: number) => void; onSelectRegion: (name: string) => void; onSelectCivilization: (name: string) => void;
}) {
  const scope = `${seatId}:${currentTurn}`;
  const [page, setPage] = useState({ scope, limit: PAGE });
  if (page.scope !== scope) setPage({ scope, limit: PAGE });
  const limit = page.scope === scope ? page.limit : PAGE;
  const prefix = bundle.history.filter((s) => s.turn <= currentTurn && s.scholarship?.learning_services != null);
  if (!prefix.length) return null;
  const exact = snapshot?.turn === currentTurn ? exactSnapshot(bundle, currentTurn) : null;
  const bounds = [bundle.world_state.regions.length, bundle.world_state.civilizations?.length ?? 0, bundle.world_state.scholarship?.seats?.length ?? 0] as const;
  const data = learningServicesAt(exact, seatId, seat, ...bounds);
  const occurrences = new Map<number, number>();
  for (const row of bundle.history) occurrences.set(row.turn, (occurrences.get(row.turn) ?? 0) + 1);
  const history = prefix.filter((s) => occurrences.get(s.turn) === 1).sort((a, b) => b.turn - a.turn);
  const regionName = seat && bundle.world_state.regions[seat.region]?.name;
  const civName = (id: number) => bundle.world_state.civilizations?.[id]?.name;
  const status = (source: number) => data && source < data.frame.captured_turn - 1 ? "Last retained record" : "Recorded";
  return <section className="systems-stack" style={{ overflowWrap: "anywhere" }} aria-label="Academy service evidence">
    <h4>Academy service and supplies · snapshot {currentTurn}</h4>
    {!data ? <p className="systems-note">Service evidence is not observed or unavailable for this seat at the selected snapshot.</p> : <>
      <p className="systems-note">{data.frame.active ? "Service is active." : "Service is paused or unavailable in this mode; retained receipts keep their original dates."} Paid crafts enter this academy&apos;s holdings in Phase 10. Teaching can use those supplies in a later native work phase; purchases and use are separate movements.</p>
      <p className="systems-note">Scholar and learner counts are native upper bounds, not available work or observed enrollment. Work is in scholar-days; each delivered day models up to eight learner-equivalents. Reserved work can reduce ordinary scholar income. The modeled service is not an individual student roster.</p>
      {regionName && seat && <p>Seat #{seatId}, founded in source turn {seat.founded_turn} · <button type="button" className="systems-link" onClick={() => onSelectRegion(regionName)}>{regionName}</button></p>}
      <h4>Academy-held crafts</h4>
      {data.inventory ? <p>{data.inventory.retired ? "Retired holding" : "Held now"}: {value(data.inventory.held)} · Cumulative purchased {value(data.inventory.purchased_total)} · Used {value(data.inventory.used_total)} · Lost {value(data.inventory.lost_total)}.</p> : <p className="systems-note">Holding not observed for this seat incarnation.</p>}
      <h4>Supply purchase</h4>
      {data.procurement ? <>
        <p>{status(data.procurement.source_turn)} · Phase 10, simulation turn {data.procurement.source_turn}; patron {civName(data.procurement.lord) ? <button type="button" className="systems-link" onClick={() => onSelectCivilization(civName(data.procurement!.lord)!)}>{civName(data.procurement.lord)}</button> : "Not observed"}.</p>
        <p>Held before {value(data.procurement.held_before)} · Purchased {value(data.procurement.purchased)} crafts · Treasury paid {value(data.procurement.paid)} · Held after {value(data.procurement.held_after)}.</p>
        <p>Potential learner demand, upper bound {value(data.procurement.learner_upper_bound)} · Native scholars, upper bound {value(data.procurement.scholar_upper_bound)}.</p>
        <p>Market crafts {value(data.procurement.market_stock)} · Committed {value(data.procurement.market_commitments)} · Craft price {value(data.procurement.craft_price)} · Available treasury {value(data.procurement.budget_before)}.</p>
        <p>Upkeep source {value(data.procurement.upkeep_source_turn)} · Due {value(data.procurement.upkeep_due)} · Paid {value(data.procurement.upkeep_amount_paid)} · Satisfied {yes(data.procurement.upkeep_satisfied)}. Zero due and zero paid are no cash payment.</p>
        <p>Recorded purchase conditions: {data.procurement.shortfalls.length ? `${data.procurement.shortfalls.slice(0, 8).map((s) => s.replaceAll("_", " ")).join(", ") + (data.procurement.shortfalls.length > 8 ? `, ${data.procurement.shortfalls.length - 8} more` : "")}; ` : ""}{data.procurement.market_commitments !== null && data.procurement.market_stock <= data.procurement.market_commitments ? "no uncommitted market crafts; " : ""}{data.procurement.budget_before === 0 ? "available treasury was zero; " : ""}see the values above.</p>
      </> : <p className="systems-note">Purchase receipt not observed for this seat at the selected snapshot.</p>}
      <h4>Teaching work</h4>
      {data.teaching ? <>
        <p>{status(data.teaching.source_turn)} · native agent wealth-phase work in simulation turn {data.teaching.source_turn}, available to the learning effect in turn {data.teaching.available_turn}.</p>
        <p>Potential learner demand, upper bound {value(data.teaching.learner_upper_bound)} · Native scholars, upper bound {value(data.teaching.scholar_upper_bound)}.</p>
        <p>Work requested {value(data.teaching.work_requested)} · Available {value(data.teaching.work_available)} · Reserved {value(data.teaching.work_reserved)} · Delivered {value(data.teaching.work_delivered)} scholar-days.</p>
        <p>Delivered {value(data.teaching.learners_delivered)} learner-equivalents · Crafts used {value(data.teaching.crafts_used)} · Held before {value(data.teaching.held_before)} → after {value(data.teaching.held_after)}.</p>
        <p>Recorded conditions: {data.teaching.upkeep_satisfied === false ? "upkeep was not satisfied; " : ""}{data.teaching.upkeep_applies === false ? "previous upkeep did not apply to this patron; " : ""}{data.teaching.held_before === 0 ? "no crafts were held before work; " : ""}{data.teaching.work_available !== null && data.teaching.work_available < data.teaching.work_requested ? "native available work was below the request; " : ""}{data.teaching.work_reserved !== null && data.teaching.work_delivered !== null && data.teaching.work_delivered < data.teaching.work_reserved ? "delivered work was below the reservation; " : ""}{data.teaching.work_delivered === null ? "actual delivery is not observed; " : ""}see the dated values above.</p>
        <p>Upkeep source {value(data.teaching.upkeep_source_turn)} · Due {value(data.teaching.upkeep_due)} · Paid {value(data.teaching.upkeep_amount_paid)} · Satisfied {yes(data.teaching.upkeep_satisfied)} · Applies to this patron {yes(data.teaching.upkeep_applies)}. Native work observations dropped: {value(data.teaching.native_dropped)}.</p>
      </> : <p className="systems-note">Teaching receipt not observed for this seat at the selected snapshot.</p>}
      <h4>Supply interruption</h4>
      {data.loss ? <p>Source turn {data.loss.source_turn}: {data.loss.reason.replaceAll("_", " ")} · held before {value(data.loss.held_before)}, lost {value(data.loss.lost)}, held after {value(data.loss.held_after)}.</p> : <p className="systems-note">No matching loss receipt retained at this snapshot; missing evidence is unknown.</p>}
    </>}
    <h4>Saved service history through snapshot {currentTurn}</h4>
    <p className="systems-note">Select a saved snapshot to inspect its own record. Missing rows remain unknown; retained receipts can repeat while paused.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Academy service history through snapshot ${currentTurn}`}><thead><tr><th>Snapshot</th><th>Held</th><th>Purchase source / crafts / paid</th><th>Work source / delivered / learner-equivalents</th><th>Loss source / crafts</th></tr></thead><tbody>
      {history.slice(0, limit).map((s) => { const r = learningServicesAt(s, seatId, seat, ...bounds); return <tr key={s.turn}>
        <td><button type="button" className="systems-link" onClick={() => onSeek(s.turn)}>{s.turn}</button></td>
        <td>{value(r?.inventory?.held)}</td><td>{r?.procurement ? `${r.procurement.source_turn} / ${value(r.procurement.purchased)} / ${value(r.procurement.paid)}` : "Not observed"}</td>
        <td>{r?.teaching ? `${r.teaching.source_turn} / ${value(r.teaching.work_delivered)} / ${value(r.teaching.learners_delivered)}` : "Not observed"}</td>
        <td>{r?.loss ? `${r.loss.source_turn} / ${value(r.loss.lost)}` : "Not observed"}</td></tr>; })}
    </tbody></table></div>
    {limit < history.length && <button type="button" className="phase75-ghost-button" onClick={() => setPage({ scope, limit: limit + PAGE })}>Show more service snapshots ({history.length - limit} remaining)</button>}
  </section>;
}
