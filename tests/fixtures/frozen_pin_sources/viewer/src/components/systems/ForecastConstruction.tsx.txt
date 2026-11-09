import type { HarvestForecastReport } from "../../types";
import { estimatorMetadataAt } from "../../lib/forecastDecision";

const show = (n: number) => n === 0 ? "0" : Math.abs(n) < .001 ? n.toExponential(3) : n.toLocaleString(undefined, { maximumFractionDigits: 4 });

/** Underlying issue-time construction is not part of the report received by an actor. */
export function ForecastConstruction({ report, sourceTurn, regions }: { report: HarvestForecastReport; sourceTurn: number; regions: Array<{ name: string }> }) {
  const m = estimatorMetadataAt(report, sourceTurn, regions.length);
  if (!m) return null;
  return <details><summary>Underlying estimator construction (not recipient-known)</summary>
    <p>Issue turn {m.issued_turn}; reported issuer {regions[m.reported_issuer_region].name}; estimate origin {regions[m.estimate_origin_region].name}; policy {m.policy}; preparation {m.preparation_policy}.</p>
    <p>Observation window {m.observation_window} turns; normalized production ÷ demand observations: {m.observations.map(([turn, value]) => `T${turn}: ${show(value)}`).join(", ")}.</p>
    <p>Season multiplier {show(m.season_multiplier)} · shortfall ratio {show(m.shortfall_ratio)} · noise draw {show(m.noise_draw)} · base delivery lag {m.base_delivery_lag} · extra delay {m.extra_delivery_delay}.</p>
    <p>Claimed risk {show(m.claimed_probability)} · confidence {show(m.claimed_confidence)} · predicted ratio {show(m.claimed_predicted_ratio)}. This construction is separate from the actor-known decision report.</p>
  </details>;
}
