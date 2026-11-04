/** Additive v1 observation reader. Invalid/unsupported records are unknown, including live data. */
import type { Bundle, RegionalPopulationSnapshot, TurnSnapshot } from "../types";
import { validatedRegionalPopulation } from "./bundleValidation";

export function readRegionalPopulation(bundle: Bundle, snapshot: TurnSnapshot | null): RegionalPopulationSnapshot | null {
  return snapshot ? validatedRegionalPopulation(snapshot.regional_population, snapshot.turn,
    bundle.world_state.regions.length, bundle.world_state.civilizations.length) : null;
}

export interface WeightedFood {
  value: number | null; observedPopulation: number | null; eligiblePopulation: number | null;
  observedRegions: number | null; eligibleRegions: number | null;
}
/** Civilization selection uses ONLY Phase 2 ownership, never completed ownership. */
export function populationWeightedFood(bundle: Bundle, snapshot: TurnSnapshot | null, civilization?: string): WeightedFood {
  const unknown = { value: null, observedPopulation: null, eligiblePopulation: null, observedRegions: null, eligibleRegions: null };
  const weights = readRegionalPopulation(bundle, snapshot)?.food_weights;
  if (!weights) return unknown;
  const owner = civilization === undefined ? undefined : bundle.world_state.civilizations.findIndex((civ) => civ.name === civilization);
  if (owner === -1) return unknown;
  const ratios = snapshot?.food?.sufficiency;
  const validRatios = Array.isArray(ratios) && ratios.length === weights.counts.length;
  let numerator = 0, observedPopulation = 0, eligiblePopulation = 0, observedRegions = 0, eligibleRegions = 0;
  weights.counts.forEach((population, index) => {
    if (owner !== undefined && weights.controller_ids[index] !== owner) return;
    eligiblePopulation += population; eligibleRegions++;
    const ratio = validRatios ? ratios[index] : null;
    if (typeof ratio !== "number" || !Number.isFinite(ratio) || ratio < 0) return;
    observedPopulation += population; observedRegions++; numerator += population * ratio;
  });
  const value = observedPopulation > 0 ? numerator / observedPopulation : null;
  if (![numerator, observedPopulation, eligiblePopulation].every(Number.isFinite)) return unknown;
  return { value: value !== null && Number.isFinite(value) ? value : null,
    observedPopulation, eligiblePopulation, observedRegions, eligibleRegions };
}
export function weightedFoodNote(food: WeightedFood): string {
  const value = (n: number | null) => n === null ? "unknown" : String(n);
  return `Phase 2 agent-population weights and ownership; known-ratio denominator ${value(food.observedPopulation)} / ${value(food.eligiblePopulation)} eligible agents, ${value(food.observedRegions)} / ${value(food.eligibleRegions)} regions. Unknown ratios are excluded, never zero. Zero denominator or missing weights is unknown.`;
}
