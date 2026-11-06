/**
 * The recovery chain's natural records (template seed 23, eleven snapshots of the
 * chain of granary project 0 in region 7, Sapphire Coast; see the fixture's note)
 * as a bundle, and constructed variants of it (labelled in each test).
 */
import natural from "../../__fixtures__/recovery_chain_natural_records.json";
import type { Bundle } from "../../types";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Natural = { regions: string[]; civilizations: string[]; snapshots: Array<Record<string, any>> };
const NATURAL = natural as unknown as Natural;
export const REGIONS = NATURAL.regions;
export const TURNS = NATURAL.snapshots.map((s) => s.turn as number);
/** Region indices of the natural chain. */
export const SAPPHIRE = 7;
export const IRON_PEAKS = 1;

/** A bundle of the natural snapshots; ``edit`` may change each copied snapshot (constructed variants). */
export function chainBundle(edit?: (snapshot: Record<string, any>) => void): Bundle {
  const history = structuredClone(NATURAL.snapshots);
  if (edit) history.forEach(edit);
  return { world_state: { regions: REGIONS.map((name) => ({ name })), civilizations: NATURAL.civilizations.map((name) => ({ name })) },
    history } as unknown as Bundle;
}

export function snapshotOf(bundle: Bundle, turn: number) {
  return bundle.history.find((s) => s.turn === turn)!;
}

/** Drop packages from every snapshot (switched off for the run). */
export const without = (...keys: string[]) => (s: Record<string, any>) => {
  for (const k of keys) {
    if (k === "grain_storage") delete s.grain_reserves.storage;
    else delete s.livelihoods[k];
  }
};
