/** Test-only core scaffolding around byte-sourced controlled observations. No production fallback. */
import observations from "./transaction_observations.json";
import type { TurnSnapshot } from "../types";

export function transactionFixture(name: keyof typeof observations): TurnSnapshot[] {
  return structuredClone(observations[name].history).map((row) => ({ civ_stats: {}, region_control: {}, relationships: {}, ...row })) as unknown as TurnSnapshot[];
}
