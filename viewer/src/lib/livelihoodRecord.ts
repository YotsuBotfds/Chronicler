import { isRecord } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/**
 * The shared envelope of the strict `*At` livelihood readers: the snapshot's
 * `livelihoods` record must be a record of `schema_version` 1, and its `key`
 * entry a record of `schema_version` 1. Returns that entry, or null.
 *
 * Only the envelope: each reader keeps its own source-turn rule (some date a
 * record by `source_turn + 1`, others by `completed_turn`) and field checks.
 */
export function readLivelihoodRecord(snapshot: TurnSnapshot | null | undefined, key: string): Record<string, unknown> | null {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null | undefined)?.livelihoods;
  if (!isRecord(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods[key];
  return isRecord(x) && x.schema_version === 1 ? x : null;
}
