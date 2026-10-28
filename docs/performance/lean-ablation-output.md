# Lean exact-checkpoint ablation output

The internal `--ablation-output` profile omits only post-run presentation
exports that the ablation orchestrator immediately deletes: the compiled
chronicle, final raw world save, viewer bundle and observational language and
historiography exports. Ordinary execution defaults to the existing full
profile. This implements the boundary registered in
[lean-ablation-preregistration.md](lean-ablation-preregistration.md).

The profile requires a compatible exact checkpoint, a decision-ablation arm,
`--simulate-only` and the local narrator. It is output-only and may override the
parent checkpoint's ordinary output profile. It changes no simulation settings.
`run_ablation_arms` uses it by default; `lean_output=False` or the orchestrator's
`--full-output` retains the full worker path for comparison.

Every turn, snapshot, event, inherited history record, memory update, reflection,
periodic writer and checkpoint still runs. Final-turn forced settlement
identification, the final native validation snapshot and writer close remain
in the same order. The lean path calls the existing event Arrow writer directly
and writes the existing four-field `fork.json` receipt. The full path continues
to obtain the event file through `write_bundle`. Compression and retained files
are identical. This first slice deliberately leaves periodic state/memory
serialization in place; further changes need their own equivalence proof.

Before compressing or deleting any output, the orchestrator checks the actual
receipt's seed, completed horizon and exact arm/start/fork turn. Missing or
malformed receipts, event serialization errors, worker launch errors and nonzero
exits produce a failed manifest and preserve that fork's artifacts and logs.
Plain checkpoints are deleted only after the whole study succeeds, so a later
seed's failure cannot erase an earlier seed's retry inputs. Existing output
roots remain protected against overwrite. Manifest schema, identities, seed and
fork rules, 20-turn windows, input hashes and causal criteria are unchanged.

## Focused correctness evidence, 2026-10-28

Source base `ac38e80e`; candidate worktree `lead/lean-ablation`; no native edits.
The preregistration was committed as `c79dcea2` before production edits.
The qualified extension SHA-256 was
`e7ec77283075cb9b817ad47490fc98a3e77685451bbcd4ce8f5b8bcad9db5867`.
Both candidate and qualified source have Rust tree
`adbe580cbeda6843b77d335e73e1ae10f7be6a9f`.

- **55 tests passed in 4.10 s:** profile restrictions and resume classification,
  ordinary decision-ablation/manifest checks, both orchestrator output paths,
  wrong horizon/seed/arm, missing receipts/events, launch failures, worker exits,
  failed manifests, retained checkpoints and no-overwrite destinations.
- **2 real native tests passed in 27.09 s:** one shared 9-turn checkpoint forked
  to completion 18, comparing every completed boundary and final state. All
  persisted world fields, entire native checkpoint bytes (including queues and
  RNG), memories, inherited history, chronicle entries, reflections, pending
  injections, turn seeds and forced-settlement calls match. Language and
  historiography systems were enabled. Raw and compressed event bytes and
  `fork.json` bytes match.
- The second native fixture executes actual `run_ablation_arms` subprocesses
  from a 101-turn checkpoint through completion 122, for `needs` and `kin_roots`,
  full and lean. Manifest input hashes, complete event prefixes, fork receipts,
  needs/cohort results, diagnostic counts and 20-turn windows match through the
  actual downstream loaders. It uses one seed for equivalence, not scientific
  qualification or an effect estimate.

Initial fixture failures were corrected before the passing result: the carried
memory object is not a Pydantic model; parent/child thread environments must
match; the explicit local narrator belongs in a programmatic checkpoint's
output settings. The first real test also caught the required event writer
being coupled to bundle output; the lean path now invokes that unchanged writer.

Commands used one-thread environments and the qualified interpreter, with this
worktree's `src` first on `PYTHONPATH`:

```sh
python -m pytest -q tests/test_ablation_output.py tests/test_decision_ablation.py tests/test_batch_manifest.py
python -m pytest -q tests/test_ablation_output_native.py
```

These correctness runs were under concurrent host load. They establish no
wall-clock improvement. Whole-worker and whole-orchestrator paired measurements
remain required on immutable source in a reserved quiet window; report output
bytes before cleanup and after retention separately. No full milestone gate is
claimed by this output-policy fixture.

## Same-source paired measurement

Measured source `6f0e549af44a17c8ba91b168bdbd83d3940dcab8` remained clean
throughout the experiment; package digest
`9a140460f398f525bf9de7b5e94278111275f611d85dcb5ce519e6ef445f5ae9`.
The matched extension is the `e7ec7728…` release identified above. Environment:
CPython 3.13.5, Linux x86-64, five CPUs in the reported affinity mask; sequential
workers with Rayon, OpenBLAS, OMP and MKL capped to one thread, hash seed zero.
The complete environment and package versions are in the receipts.

Two ordinary fresh template parents (seeds 42 and 43, four civilizations,
eight regions, 500 turns) supplied exact checkpoints. Direct comparisons used
forks 100 and 400. Each subprocess continued source ticks `T+1 .. T+21`, through
completion `T+22`; the causal window remains ticks `T+1 .. T+20`, with final-turn
settlement detection outside it. Each cohort has five interleaved full/lean
pairs. Worker time includes a fresh interpreter, imports, exact restore,
simulation and exports. Whole-fork time also includes the unchanged receipt
validation/compression/cleanup. Diagnostic inventory hashing between these
stages is excluded. No profile trims runtime history or reduces the horizon.

| Seed / fork | Full whole-fork median (s) | Lean median (s) | Median paired full/lean | Pair range | Precleanup bytes full / lean |
| --- | ---: | ---: | ---: | --- | ---: |
| 42 / 100 | 1.925 | 1.555 | 1.157× | 0.966–1.328× | 4,792,194 / 2,468,128 |
| 42 / 400 | 2.509 | 1.941 | 1.244× | 1.218–1.551× | 12,465,082 / 6,401,607 |
| 43 / 100 | 1.576 | 1.395 | 1.160× | 0.975–1.203× | 5,742,250 / 3,162,633 |
| 43 / 400 | 2.769 | 2.019 | 1.361× | 1.048–1.643× | 15,862,792 / 8,784,396 |

These are the **clean supplemental** worker measurements described below.
Transient output bytes fall **44.6–48.6%**. Final retained bytes are identical in
each pair: respectively 43,466; 143,738; 70,490; and 240,722 bytes. The raw Arrow
bytes before compression also match in every recorded direct pair.

Ten actual fresh-process `run_ablation_arms` invocations compare both profiles
for all four legal fork points (100/200/300/400), both seeds and `needs` plus
`kin_roots`: 16 worker processes per invocation. Downstream loaders and complete
needs/cohort results were checked after each invocation, outside the timed CLI
block; all inputs, event prefixes, receipts and oracle results match.

| Pair | Full orchestrator (s) | Lean orchestrator (s) | Full / lean |
| --- | ---: | ---: | ---: |
| 0 | 62.142 | 29.384 | 2.115× |
| 1 | 47.822 | 44.535 | 1.074× |
| 2 | 46.302 | 46.957 | 0.986× |
| 3 | 39.861 | 30.453 | 1.309× |
| 4 | 37.049 | 32.318 | 1.146× |

The **paired median is 1.146×**, or a 12.8% median paired wall-time reduction.
The range is broad and one pair reverses slightly. This supports an observed,
noisy improvement in this experiment, not a portable speedup guarantee. The
separate full/lean medians (46.302/32.318 s) must not be divided and reported as
the paired effect. Child CPU seconds are retained; they track wall time closely.
Parent generation, downstream oracle scoring and the complete scientific gate
are outside this timing comparison.

The first direct measurements overlapped a short comparator test and a
24-bundle audit by an agent omitted from the initial hold messages. Exact
overlap timestamps were unavailable. **All original direct-worker timings were
excluded**, retained as exploratory, and replaced with five clean pairs for
every seed/fork cohort using the exact same identified checkpoints. All agents
acknowledged CPU idle before any whole-orchestrator pair began. The primary
study ran 19:21:39–19:31:32 UTC; the clean worker supplement ran
19:31:51–19:33:10 UTC. Qualification supervisors paused only between atomic jobs
and resumed after the explicit completion signal. There were 242 actual native
executions including repeated timings and two parents; these represent two seed
trajectories, not 242 independent scientific samples.

A separate unchanged-default check compared ordinary full output at baseline
`ac38e80e` with candidate `6f0e549a`: 31 files matched, raw except for removal of
only `metadata.generated_at` from the bundle. It used 30 turns, three
civilizations, six regions, hybrid agents, validation sidecars, languages and
historiography. The strengthened boundary fixture also checks private contact,
hazard and artifact signals and both authoritative archive states. Together with
the incompatible-checkpoint and duplicate-arm preflight regressions, the final
focused selection passed **58 tests in 4.79 s**. Duplicate arms now fail before
creating a study, avoiding a destination collision and stranded running manifest.

### Retained evidence and reproduction

Generated evidence remains outside Git under
`/workspace/chronicler-lean-ablation-evidence/`:

| Artifact | SHA-256 |
| --- | --- |
| `paired-500-42-43/benchmark.json` | `d46435b0f3388c056ebafe54f9c0bb6399671c3451c7d5b3c0cbc6c874f9ca3c` |
| `quiet-supplement-500-42-43/benchmark.json` | `cbbf701b325bc8b0967d1edd0a21fafad8536b087197ca21cb2888bd2268687d` |
| `quiet_supplement.py` | `01c576b36690d197a90df96507df6441904aefed2431ab37810913b2fce444f6` |
| `environment-disclosure.json` | `afdccde9b7447fbc307ed9e1528edf391e3c5f6da029c77d606e46df6498910e` |
| `default-identity/identity.json` | `1372dd94121c1230a8c07c4a0c0d5d6fc22c5ffbf1c1cd7f60195e1ea5cb1096` |

The receipts retain exact commands, runner/native/source/package identities,
parent-checkpoint hashes and headers, failures/status, completed horizons,
precleanup and retained inventories, every timing pair and downstream reports.
The original runner SHA-256 is
`d777a6617e5a32d542f7683311979ae21036df66c1b1cd0b73ae9d241adcd8ed`.
The supplemental source is separately retained and hashed; the original
measurements were not overwritten.

To reproduce on a clean immutable checkout and matching native release, reserve
an otherwise idle host and run:

```sh
RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONHASHSEED=0 python scripts/benchmark_lean_ablation.py \
  --source-root /path/to/frozen-source --output-root /path/to/new-external-evidence \
  --turns 500 --seeds 42,43 --trials 5
```

The remaining 2.5–8.8 MB of lean transient output per sampled fork is still mostly
discarded; periodic world/memory and validation writers remain active. A further
output-policy experiment could examine those writers without trimming runtime
history, but it must separately prove carried memory/archive state, checkpoint
payload semantics and callbacks. Reusing worker processes may amortize imports
later, with a separate reset/isolation contract. Neither follow-up is enabled by
this change.
