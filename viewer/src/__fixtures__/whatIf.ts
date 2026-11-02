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

/** Constructed source envelope for recipe privacy/identity tests only. */
export function recipeManifest(): WhatIfManifest {
  return { ...whatIfManifest, source: {
    checkpoint: { name: "/private/run/common.ckpt", byteLength: 500, sha256: "f".repeat(64) },
    token: "PRIVATE_TOKEN",
    header: { exact: true, turn: 2, seed: 42,
      identity: { source: { git_sha: "c".repeat(40), package_digest: "d".repeat(64), package_dir: "/private/source" },
        native: { status: "absent", state_layouts: {} },
        environment: { python: "3.13.5", implementation: "CPython", machine: "x86_64",
          packages: { numpy: "2.5.4", API_TOKEN: "PRIVATE_TOKEN" },
          thread_env: { PYTHONHASHSEED: "0", OMP_NUM_THREADS: "1", API_TOKEN: "PRIVATE_TOKEN" },
          endpoint: "https://private.example/?token=PRIVATE_TOKEN" } },
      run_config: { simulation_args: { agents: "hybrid", grain_reserves: true, regions: 8, civs: 4,
        tuning_overrides: { "grain_reserves.shortfall_priority": 0 }, scenario: "/private/maps/world.yaml",
        token: "PRIVATE_TOKEN" }, output_args: { simulate_only: true, output: "/private/output", api_key: "PRIVATE_TOKEN" } } },
  } };
}
