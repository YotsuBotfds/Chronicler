import type { CompletedRun } from "../lib/completedRunComparison";
import { exactSnapshot } from "../lib/historyComparison";
import { learningServicesAt } from "../lib/learningServices";

const value = (v: number | null | undefined) => v == null ? "Not observed" : v === 0 ? "0"
  : Math.abs(v) < .001 ? v.toExponential(3) : v.toLocaleString(undefined, { maximumFractionDigits: 3 });
export function AcademyRunComparison({ left, right, turn }: { left: CompletedRun; right: CompletedRun; turn: number }) {
  // Only selected-snapshot receipts introduce seats. Final-world records solely validate identity.
  const frames = [left, right].map((run) => exactSnapshot(run.bundle, turn)?.scholarship?.learning_services);
  if (!frames.some(Boolean)) return null;
  return <section className="academy-run-comparison" aria-label="Academy supplies and service comparison">
    <h3>Academy supplies and delivered work · snapshot {turn}</h3>
    <p>Each run shows its own dated seat incarnations. Purchases occur after native work and supply a later turn.
      Potential learners are an upper bound; missing delivery is unknown even when no work was requested.
      These observations do not establish household welfare or general service effectiveness.</p>
    <div className="completed-compare-inputs">{([left, right] as const).map((run, index) => {
      const snapshot = exactSnapshot(run.bundle, turn);
      const frame = frames[index];
      const seats = run.bundle.world_state.scholarship?.seats ?? [];
      const ids = [...new Set([frame?.inventories, frame?.procurement_receipts, frame?.teaching_receipts, frame?.supply_losses]
        .flatMap((rows) => Array.isArray(rows) ? rows.flatMap((row) => row && Number.isSafeInteger(row.seat_id) ? [row.seat_id] : []) : []))];
      const readings = ids.map((id) => ({ id, reading: learningServicesAt(snapshot, id, seats[id] ?? null,
        run.bundle.world_state.regions.length, run.bundle.world_state.civilizations.length, seats.length) }))
        .filter(({ reading }) => reading && (reading.inventory || reading.procurement || reading.teaching || reading.loss));
      return <div key={index} className="completed-compare-input"><h4>{index === 0 ? "Left run" : "Right run"}</h4>
        {!readings.length ? <p>No validated academy receipts at this exact snapshot. Service, supplies and absence of delivery stay unknown.</p>
          : readings.map(({ id, reading: r }) => <article key={id}>
            <h4>{(r!.inventory ?? r!.procurement ?? r!.teaching ?? r!.loss)!.seat_name} · seat #{id}</h4>
            <p>Founded in source turn {(r!.inventory ?? r!.procurement ?? r!.teaching ?? r!.loss)!.founded_turn}.
              {r!.frame.active ? " Service active." : " Service paused or unavailable; retained receipts keep their source dates."}</p>
            <p>Held crafts: {value(r!.inventory?.held)}{r!.inventory?.retired ? " (retired holding)" : ""}.</p>
            <p>Purchase source tick: {value(r!.procurement?.source_turn)} · Crafts bought: {value(r!.procurement?.purchased)} · Treasury paid: {value(r!.procurement?.paid)}.</p>
            <p>Market crafts: {value(r!.procurement?.market_stock)} · Committed: {value(r!.procurement?.market_commitments)} · Price: {value(r!.procurement?.craft_price)} · Budget: {value(r!.procurement?.budget_before)}.</p>
            <p>Recorded purchase conditions: {r!.procurement ? r!.procurement.shortfalls.map((s) => s.replaceAll("_", " ")).join(", ") || "None recorded" : "Not observed"}.</p>
            <p>Work source tick: {value(r!.teaching?.source_turn)} · Requested: {value(r!.teaching?.work_requested)} · Delivered: {value(r!.teaching?.work_delivered)} scholar-days.</p>
            <p>Learners delivered: {value(r!.teaching?.learners_delivered)} · Potential learners (upper bound): {value(r!.teaching?.learner_upper_bound)} · Crafts used: {value(r!.teaching?.crafts_used)}.</p>
            {r!.teaching?.work_delivered == null && <p>Actual native delivery is not observed.</p>}
          </article>)}
      </div>;
    })}</div>
  </section>;
}
