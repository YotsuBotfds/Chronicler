import type { HarvestEstimatorMetadata, HarvestForecastReport, HarvestProcurementDecisions } from "../expansionTypes";
import type { TurnSnapshot } from "../types";
import { finite, amount as number, safeCount as integer } from "./recordGuards";
const probability = (v: unknown): v is number => number(v) && v <= 1;
const nullable = (v: unknown) => v === null || number(v);
const index = (v: unknown, n: number) => integer(v) && v < n;
const text = (v: unknown) => typeof v === "string" && v.length <= 512;

/** Validate only this child observation; absence never becomes a zero decision. */
export function forecastDecisionsAt(snapshot: TurnSnapshot | null, regions: number, civs: number): HarvestProcurementDecisions | null {
  const parent = snapshot?.harvest_forecasts, f = parent?.procurement_decisions;
  if (!snapshot || !parent || !f || !integer(parent.source_turn) || parent.source_turn !== snapshot.turn - 1
    || f.schema_version !== 1 || f.source_turn !== parent.source_turn || f.available_turn !== snapshot.turn
    || typeof f.mode !== "string" || f.goods_units !== "model_food_goods" || f.currency_units !== "model_treasury_coins"
    || !Array.isArray(f.rows)) return null;
  const seen = new Set<number>();
  for (const row of f.rows) {
    if (!row || row.turn !== f.source_turn || !row.decision) return null;
    const d = row.decision;
    if (!index(d.region, regions) || seen.has(d.region) || !index(d.owner, civs)
      || !(d.controller === null || index(d.controller, civs)) || !Array.isArray(d.reports)
      || !nullable(d.target_before) || !nullable(d.food_demand) || !nullable(d.pending_inbound)
      || ![d.requested_target, d.feasible_target, d.granary_stock, row.purchased_grain, row.committed_grain].every(number)
      || !integer(d.opening_budget) || !integer(row.paid) || row.attempted !== null) return null;
    seen.add(d.region);
    const reports = new Set<string>();
    for (const r of d.reports) {
      if (!r || !text(r.id) || !r.id || reports.has(r.id) || !index(r.source_region, regions) || r.recipient_region !== d.region
        || ![r.issued_turn, r.planned_delivery_turn, r.delivered_turn, r.expires_turn, r.target_start, r.target_end].every(integer)
        || !(r.issued_turn < r.planned_delivery_turn && r.planned_delivery_turn <= r.delivered_turn && r.delivered_turn <= f.source_turn && f.source_turn <= r.expires_turn)
        || !(r.issued_turn < r.target_start && r.target_start <= r.target_end && r.target_end === r.expires_turn)
        || !probability(r.probability) || !probability(r.confidence) || !number(r.predicted_ratio)
        || !text(r.issued_event_id) || !text(r.delivered_event_id)) return null;
      reports.add(r.id);
    }
  }
  return f;
}

/** Issue-time underlying construction, not information received by the decision maker. */
export function estimatorMetadataAt(report: HarvestForecastReport, sourceTurn: number, regions: number): HarvestEstimatorMetadata | null {
  const m = report.estimator_metadata;
  if (!m || m.schema_version !== 1 || !integer(m.issued_turn) || m.issued_turn !== report.issued_turn || m.issued_turn > sourceTurn
    || !index(m.reported_issuer_region, regions) || m.reported_issuer_region !== report.source_region || !index(m.estimate_origin_region, regions)
    || !["normal", "withhold", "shuffle"].includes(m.policy) || !["fixed", "local_credibility"].includes(m.preparation_policy)
    || !(m.base_delivery_lag === 1 || m.base_delivery_lag === 2)
    || !integer(m.extra_delivery_delay) || m.extra_delivery_delay > 12
    || m.issued_turn + m.base_delivery_lag + m.extra_delivery_delay !== report.delivery_turn || m.observation_window !== 6
    || !Array.isArray(m.observations) || m.observations.length < 3 || m.observations.length > 6
    || !m.observations.every((row, i) => Array.isArray(row) && row.length === 2 && integer(row[0]) && row[0] <= m.issued_turn && m.issued_turn - row[0] < 6 && number(row[1])
      && (i === 0 || row[0] > m.observations[i - 1][0]))
    || !number(m.season_multiplier) || !number(m.shortfall_ratio) || !finite(m.noise_draw)
    || !probability(m.claimed_probability) || !probability(m.claimed_confidence) || !number(m.claimed_predicted_ratio)
    || m.claimed_probability !== report.probability || m.claimed_confidence !== report.confidence || m.claimed_predicted_ratio !== report.predicted_ratio) return null;
  return m;
}
