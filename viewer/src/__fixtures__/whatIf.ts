import { comparisonBundle } from "./completedRunHistory";
import type { WhatIfManifest, WhatIfPair } from "../lib/whatIf";
export const whatIfManifest: WhatIfManifest = {
  schema_version: 1, request_id: "fixture-pair", source: { checkpoint: { sha256: "f".repeat(64) } },
  semantics: "exact_checkpoint_pair", mode: "hybrid", seed: 42,
  start_turn: 2, end_turn: 5, turns: 3,
  intervention: { command: "set", civ: "A", stat: "stability", before: 60, value: 80 },
};
export const whatIfPair: WhatIfPair = {
  manifest: whatIfManifest,
  baseline: { bundle: comparisonBundle(), identity: { name: "baseline.json", byteLength: 123, sha256: "a".repeat(64) }, label: "Unchanged continuation" },
  intervention: { bundle: comparisonBundle(), identity: { name: "intervention.json", byteLength: 124, sha256: "b".repeat(64) }, label: "Stability intervention" },
};
