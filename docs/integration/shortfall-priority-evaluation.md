# Shortfall purchasing priority: bounded evaluation

Source base: `061594a0606b9a9dfdbd1a63de2afb7dfcc3c3db`, 2026-11-01.
This evaluates the existing `grain_reserves.shortfall_priority` switch, with
granaries enabled. It changes no policy, numeric parameter or default.

## Declared matrix (before execution)

All constructed cases use template seed 42 only as a map/identity scaffold,
then explicitly replace ownership, populations, reserve history, markets and
observed food. They are production-kernel examples, **not naturally generated
worlds**. Eight regions remain; only source 0 and destinations 1/2 have people
(20 each). Source 0 holds 80 grain, demand 10, price 0.125; it has no reserve
target. Destinations have equal observed harvest histories (12 observations,
mean 0.5, square mean 0.5) giving target 40 after observation. Destination 1
starts empty, destination 2 with 2 grain. All markets otherwise hold zero.
The owner has 30 treasury, permitting one coin (8 sent grain). All other
treasuries are zero. Native commitments are absent in these kernel fixtures.
Fixture adjacency lists are replaced with a star rooted at source 0, and terrain
is set to plains. No route monkeypatch is used: destinations 1/2 are adjacent to source 0;
the disconnected case removes destination 2's edges. Arms differ only in the
tuning override (omitted, 0, 1). Probe the purchase at turn 30, then call actual
Phase 2 release/storage at 31 with the declared next food and close its ledger.
No extra purchasing occurs at 31. Current food is not changed by purchasing.

| Case | Current food 1/2 | Next food 1/2 | Declared off/on purchase and outcome |
|---|---|---|---|
| scarce_budget | 1 / 0.6 | 1 / 0 | Empty 1 / hungry 2; priority raises next food 2, adds transit loss only if route differs (both one hop here). |
| multiple_hungry | 0.5 / 0.2 | 0 / 0 | Empty 1 / most hungry 2; food 1 worsens, food 2 improves; total relief need not improve because reserve rules cap release. |
| future_shortage | 1 / 0.6 | 0 / 1 | Empty 1 / hungry 2; priority hurts next food 1 when the observed shortage moves. |
| disconnected | 1 / 0.6 | 1 / 0 | Destination 2 unreachable; both buy 1, with no food 2 benefit. |
| ownership_change | 1 / 0.6 | 1 / 0 | Buy 1 / buy 2, then transfer 2 to another ruler; surviving grain feeds its new subjects. Old ruler loses the purchased reserve. No conquest destruction is implied by this controller-only fixture. |
| no_supply | 1 / 0.6 | 1 / 0 | Source stock 40 (the retention floor); neither arm buys; no benefit. |

For every case record destination-level release, food, reserve, treasury,
market extraction, transit/storage loss and captured counters. Check grain
balance, treasury costs, market retention, unchanged purchase-time food,
unchanged Python RNG, repeated-arm determinism, and omitted/zero parity
(remove only that override for comparison). Also serialize at the post-buy
boundary and require identical kernel continuation; this is a World JSON
check, **not** an exact native checkpoint qualification.

Actual-native lane: a separate, fixed **naturally generated template world**,
seed 42, 8 regions, 4 civilizations, 60 turns, hybrid agents, granaries enabled,
validation sidecar, resource checks. Run omitted, 0, 1, 1-repeat with the existing
grain probe. Zero and one save exact checkpoints at 30; resume each with the
ordinary CLI to 60 and compare completed outputs using the existing checkpoint
comparison (excluding the read-only probe JSONL, which a CLI resume does not
emit). Omitted/zero compare after deleting only the priority key in decoded
state/bundle; one/repeat compare all simulation outputs. Checkpoint files and
run manifests are excluded as in existing identity tooling. Before execution,
verify the real compiled extension and Rust tree
`edb263686adb7ea5e23864146a5f7d0c5a163da4`; use the prebuilt runtime from
`32ac587908b28167e45ff105f62ace988fbb8e12`, without rebuilding. This is source
compatible native wiring/continuation evidence, not a fresh build of this
Python branch. Fix `PYTHONHASHSEED=0`, `RAYON_NUM_THREADS=1`,
`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`; seed 42 throughout.

Native outcomes are deliberately not predicted to improve: report both arms'
shortage, deaths, food departures, treasury and reserve/loss metrics and their
paired difference. Record whether purchases and releases actually occur and
whether the policy changes any purchase destination. A neutral run is useful
wiring evidence but cannot validate benefits on naturally generated shortages.
No selection of a more favorable seed after this result, population/scientific
gate, policy tuning or default promotion is part of this evaluation.

External receipts, raw outputs and the preregistered copy belong under
`/workspace/shared/chronicler-next-development-evidence/shortfall-evaluation`.
The source evaluator is `scripts/shortfall_priority_evaluation.py`; run its
`constructed` and `native` subcommands into fresh output directories.

## Observed results (2026-11-01)

The external preregistered copy, saved before runs, has SHA-256
`a8f16bcbc45a7f9c12b60c368597922e8489a6d22d8e4446639fa83cff479aad`.
The adjacency sentence above clarifies the implemented construction; the case
matrix, parameters and outcome declarations did not change after observation.

All six matched constructed inputs balance their resource ledgers. Omitted
and zero priority are identical after removing only the override. Both repeats
and post-purchase JSON continuations are identical, without Python RNG changes.
Purchasing leaves the current food observations unchanged.

| Case | Next food 1/2, off | Next food 1/2, on | Benefit or harm in this fixture |
|---|---|---|---|
| scarce_budget | 1 / 0.2 | 1 / 0.6 | Hungry 2 receives 4 additional grain of relief. |
| multiple_hungry | 0.6 / 0.2 | 0 / 0.6 | Most hungry 2 improves; hungry 1 loses 0.6 food sufficiency. Total immediate release falls 8→6. |
| future_shortage | 0.6 / 1 | 0 / 1 | When hunger moves, priority leaves the newly hungry 1 without relief. |
| disconnected | 1 / 0.2 | 1 / 0.2 | No benefit: the hungry destination is unreachable. |
| ownership_change | 1 / 0.2 | 1 / 0.6 | New owner's subjects receive more relief; old ruler's transferred reserve rises 2→9.6. |
| no_supply | 1 / 0.2 | 1 / 0.2 | No purchase and no benefit. |

Every purchasing case spends exactly one coin, extracts 8 grain from source 0,
delivers 7.6 after 0.4 transit loss, and leaves 72 market grain, above the 40
retention floor. No-supply leaves 40. Both destinations are one hop from the
source, so transit loss is equal between arms. The multiple-hungry harm arises
from the existing release rule: a reserve below half its target releases only
to the 0.6 famine line. Concentrating 9.6 grain at 2 leaves more grain stored while
1 loses relief. The ownership case models a controller transfer only; it
does not claim to exercise conquest destruction. These examples do not measure
longer-run mortality or compare policy quality across generated populations.

The fixed actual-native seed 42 world is **neutral between arms**: four
purchase-region-turns per arm, zero changed purchase-region-turns, 33.374642
grain sent, 23.279881 released, 8.746674 spoiled and 1.348086 lost in transit.
Both arms have 39.563863% short owned/populated region-turns, 9.034268% famine
region-turns, 191 deaths (15.800794 per 1,000 agent-turns), mean treasury 74.475,
and 96.18886 merchant food departures. All paired summary deltas are zero.
This confirms actual-native activation, accounting and persistence, but supplies
**no observed natural-world benefit or harm from the priority order**: the
policy did not change the realized purchases in this one world.

Actual-native continuation at 30→60 passes in both 0/1 arms, 33 compared output
files each with zero differences. Omitted/zero parity and 1/repeat each compare 46
files with zero differences. Only generated-at metadata and the declared
priority key (for omitted/zero) are normalized; resume comparisons omit the
probe-only JSONL and saved checkpoint itself, retain per-turn state handling
from the existing comparator, and compare all other available simulation
outputs including the reserve ledger. Run manifests are excluded by the
existing comparison tool. Resource checks were enabled throughout.

The real extension is CPython 3.13.5/Linux, SHA-256
`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
Both the prebuilt commit and the frozen Python worktree have the declared Rust
tree; the evaluator verifies compiled import/classes and this worktree's
Python import path. No native build or scientific/default promotion ran.

Verification: `tests/test_grain_reserves.py` on the no-native interpreter:
**62 passed, 2 native skips**, including seven new evaluator tests. The file
already belongs to the bounded Python oracle selection; this focused run is
not a complete oracle gate. The native evaluator separately executes four
fresh 60-turn processes and two 30-turn continuations (300 simulated turns).
The first attempt, `native-01`, completed its simulation processes but failed
the final evaluator assertion because the existing checkpoint helper excludes
`ckpt/` checkpoints while this CLI option writes `checkpoint_turn_30.ckpt`
beside the output. Its sole reported resume differences were those checkpoint
files; the predeclared checkpoint exclusion was corrected without excluding
any simulation data. `native-02` then passed. `native-03` repeats the same fixed
inputs after adding explicit prebuilt-source/tree and evaluator-hash receipts
and startup hash-seed enforcement; it is the final native-lane check. Only the constructed report later adds explicit per-destination release amounts;
the native lane functions are unchanged from that execution. All attempts
are retained, totaling 18 native processes and 900 simulated turns on one
declared seed, not 18 independent worlds or a seed sweep.

Reproduce from the repository root after sourcing the authorized runtime:

```bash
export PYTHONPATH="$PWD/src" PYTHONHASHSEED=0 RAYON_NUM_THREADS=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 CHRONICLER_CHECK_RESOURCES=1
"$CHRONICLER_NO_NATIVE_ENV/bin/python" -m pytest tests/test_grain_reserves.py -q
"$CHRONICLER_NO_NATIVE_ENV/bin/python" scripts/shortfall_priority_evaluation.py constructed /fresh/external/constructed
"$CHRONICLER_NATIVE_ENV/bin/python" scripts/shortfall_priority_evaluation.py native /fresh/external/native
```

External `constructed-02/constructed.json`, `native-03/native.json`,
`native-03/identity.json`, logs and a final source receipt preserve raw results.
The directory must be fresh; the evaluator does not overwrite an existing run.
