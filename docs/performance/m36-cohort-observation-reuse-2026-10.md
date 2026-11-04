# Validated M36 cohort observation reuse — 2026-10-29

Status: validated test-only change, integrated into review source `1c5728b7`, based on
`c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`. The frozen source checks below
completed after the forkserver timing window. Production source and scientific
gates are unchanged; this establishes no simulation speedup.

## Historical reason to investigate

The immutable d028 CI artifact audit attributes 86.309 seconds to
`tests/test_m36_regression.py` in the native-installed lane. The largest
four rows are:

| Existing node suffix | Recorded seconds | Outcome |
| --- | ---: | --- |
| TestInvestCultureAcceleration::test_invest_culture_events_reachable | 21.739 | pass |
| TestInvestCultureAcceleration::test_invest_culture_directional | 21.491 | skip |
| TestAssimilationTiming::test_assimilation_events_occur | 17.158 | pass |
| TestAssimilationTiming::test_assimilation_timing_distribution | 17.011 | pass |

Their 77.399 seconds are pytest testcase attribution from one historical run,
not a measured removable cost. The module has no sleeps: these tests advance
real seeded aggregate physics through `run_turn`. Its original test blob is
`a04b15cfb0e02c07dbe69be2caf7cbcb1ef9bf1b`, unchanged between d028 and c76.

Each assimilation test requests seeds 0–49 for 120 turns with the same helper,
arguments and action selector. Each invest-culture test separately requests
seeds 0–49 for 150 turns. The original skip happens after collecting the full
150-turn cohort, when either observational group has no assimilating seeds.
The acceleration mechanism also has direct unit coverage in
`test_culture.py::TestInvestCultureResolution`; this skipped row does not
establish that the direct mechanism lacks unit coverage.

A capability preflight cannot honestly predict both natural groups without
their observations. This draft adds no outcome-conditioned early skip.

## Source assessment and remaining uncertainty

Both the owner and an independent reviewer found no concrete source blocker
for reusing immutable observations within each exact pair:

- These four helpers pass no agent bridge, ecology runtime or politics runtime.
  The collection-time extension availability check does not activate native
  execution for their cohorts; ecology explicitly selects Python when runtime
  is absent.
- World generation and action selection construct local explicitly seeded
  `random.Random` objects. No advancing process-global RNG was found on this
  path. The unseeded live-start helper is outside it.
- Histories, region/civilization collections and transients belong to each
  world. History indexes are attached to their world. Ecology templates and
  event probabilities are copied. Typed Pydantic list fields receive template
  lists; runtime alias isolation remains to be checked.
- Action weights are rebuilt. Registries are initialized during imports; no
  per-world registry mutation was found. There is no autouse fixture changing
  these tests. The debug population ledger resets at turn entry.
- Climate and harvest caches appear to derive values from explicit inputs and
  fixed tables, affecting warming rather than identified outcome semantics.

Those were preregistration source findings. The validation below subsequently
checked alias isolation and observed repeated-cohort equality in the registered
order and two explicit contexts. It does not establish arbitrary-order or
all-environment equivalence.

## Test change

Two separate class-scoped fixtures collect the original 50-seed/120-turn and
50-seed/150-turn cohorts. Each calls the untouched `_make_world` and action
engine in ascending seed order with `agent_mode=None`. It checks actual
completed seed/horizon and stores only ordered `NamedTuple` observations:
integer seed/turn, the full tuple of assimilation turns, and the boolean
presence of any invest-culture event over that entire window.

No World, event, mutable list or runtime object enters the fixture result.
Duplicate assimilation turns and event order remain intact. The cohorts are
not extended, merged or substituted across horizons. The 120-turn cohort is
not inferred from a 150-turn final world.

All original test nodes, assertions, statistical bands, error messages and skip
predicates remain. Each test consumes the same event summaries its original
loop computed; repeated-cohort equivalence was verified by the checks below.
Three pure cases (two parameterized by horizon) cover exact seed/horizon/argument requests,
retained ordering/duplicates, no world/event alias after copying and immutable
observations. These contracts were unrun at draft creation and subsequently passed below.

This changes test setup reuse, not the scientific population gate's samples,
windows or policy. It is not an optimization of production simulation physics
and establishes no wall-time improvement.

## Preregistered validation after timing release

Independent source review precedes all execution. Then:

1. Run the new pure contracts with no simulation advancement.
2. Verify fresh world/template isolation and global RNG preservation on this
   exact aggregate path, including import/cache warming boundaries.
3. For every seed 0–49 and each separate 120/150 horizon, compare ordered
   primitive summaries from both original independent repetitions against the
   corresponding proposed fixture observations. Retain exact source, command,
   environment, per-seed observations and original skip reasons. A mismatch
   blocks reuse; do not edit expected outcomes or seed selection.
4. Run all four existing consumers together and each consumer alone. Keep
   native-installed and no-native environments distinct, even though these
   cohorts use Python physics; collection imports differ.
5. Run the complete M36 module and relevant CI. Preserve counts and original
   failures/skips. Measure any wall-time difference only in a separately
   controlled comparison after correctness checks.

The original four cohort executions total 27,000 requested physics turns.
The proposed two fixture computations total 13,500 requested turns, while all
assertion consumers retain their full seed/horizon observations. That is a
structural workload count conditional on safe reuse, not an observed speedup.

## Completed validation and source boundaries

The exhaustive and consumer checks tested frozen source
`57bb2bf09154b0f56fe52a9c2bccf1de8ce45f6e`. Its production package tree is
`47381a4e5181515babc978227792deb2b55618d2`, identical to base c76; its Rust
crate remains `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`.
The original test file was verified byte for byte against c76/Git blob
`a04b15cfb0e02c07dbe69be2caf7cbcb1ef9bf1b`. The tested candidate test SHA-256 is
`9f6c34872d41a3335294c6b9cd056b312a02503ef6cbd3d51de1d72e1fc1f880`.
All 13 original method nodes remain; AST checks preserve every original
assertion and skip call, with unchanged bodies for the nine other methods.

Every numerical/test process used CPU 4 and one-thread OMP/OpenBLAS/MKL/BLIS/
vecLib/NumExpr/Goto/Rayon/Python/Cargo caps, with hash seed 0. There was one
sequential validation stream, no native build, no shortened horizon and no
outcome-conditioned fast skip. Tiny per-seed observations, commands, logs,
identity/schema records and receipts are retained externally under
`m36-reuse-validation-20261029`; no raw world outputs were deleted.

| Explicit context | Python | pytest | Pydantic | Native availability |
| --- | --- | --- | --- | --- |
| No native | 3.13.5 | 9.1.1 | 2.14.1 | package spec absent |
| Installed native | 3.13.5 | 9.0.2 | 2.12.5 | real three classes and compiled module verified |

Both have NumPy 2.5.4, PyArrow 26.0.0 and SciPy 1.18.1. These are distinct
installed environments. The reused compiled submodule SHA-256 is
`fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`, from the
same qualified crate tree. Compiled origins, class identity, checkpoint schemas
and before/after hashes were verified. This is not a fresh native build or a
claim that the two dependency environments are identical.

For every seed 0–49 at each exact 120- and 150-turn horizon, original
repetition 1, original repetition 2 and the actual fixture function produced
identical ordered primitive observations in each context. Those 600 complete
world executions advanced 81,000 aggregate test turns. Observations also
matched across the two contexts. No World/Event object was shared.

Fresh generated worlds passed template/list alias-isolation checks. Cohort
snapshots preserved Python's default RNG, NumPy's legacy RNG, the three checked
generation tables and action/reaction handler names. Separate fresh startup
probes preserved both RNG states across source/native-class probes, test and
simulation imports and two unadvanced world constructions. Their boundary
starts after the standard RNG APIs initialize; this is not an exhaustive
snapshot of all module state. Actual supervisor launch metadata excludes
`PYTHONOPTIMIZE`/`-O`, and the startup probes explicitly recorded optimize=0.

| Test selection, in each context | No-native outcome | Installed-native outcome |
| --- | --- | --- |
| Four original consumers together | 3 passed, 1 skipped | 3 passed, 1 skipped |
| Each consumer alone | same per-node outcome and skip reason | same per-node outcome and skip reason |
| Complete M36 module, including three pure cases | 14 passed, 2 skipped | 15 passed, 1 skipped |

The directional skip remains **39 assimilating invest-culture seeds, zero
no-invest controls**. The no-native module additionally retains the original
hybrid-availability skip. The four consumers together advance exactly 13,500
turns in each context; each standalone consumer still advances its complete
6,000- or 7,500-turn cohort. Every consumer selection, including the full module,
passed zero non-None bridge/ecology/politics runtime arguments for those four
nodes. Counters observe `run_turn` arguments, not direct Rust internal ticks.
The complete installed-native module separately exercised its existing hybrid
comparison: 250 turns with a bridge and 250 with each off-mode native runtime.
No-native full-module execution passed no such runtime objects.

A postflight observer initially counted call-phase skips only and omitted the
no-native setup-phase availability skip. Its source and receipt remain
unchanged. V2 reconciles one final result for every collected node, reporting
the correct 14/2 versus 15/1 counts. This correction reran no test or cohort and
changed no project source, observation, predicate or original result.

The exhaustive stream receipt SHA-256 is
`5cbfcc66478f6926525c5df15d91f0944cb2a2743dc6869e8cf18d5ae2a72213`;
the corrected postflight receipt is
`a8b26889f6e7021823a6b03f8c05bde89373f9523f38175113b7e5355220bb49`.
Command durations are retained for provenance, not promoted into a speedup
comparison. Equality covers the registered original-1 → original-2 → fixture
order, not arbitrary future ordering or configuration.

## Later offline selector only

After the frozen validation completed, commit
`6662a55b1ef69d8eeac5714b439d1dcaf02dd700` added only the new pure
`TestCultureObservationIsolation` class to the existing `diagnostics` chunk.
M36 test, production and guard bytes remained identical to the frozen proof.
All slow cohort consumers stay outside the bounded selection; the 110-second
limit and import/IO allowances are unchanged.

That exact class passed under the existing guard in the real native-installed
environment: **3 passed**, guard **PASS**, no native modules loaded, no blocked
IO and zero ecology/politics factory calls. The expected collection-time
`chronicler_agents` availability import was denied before package code loaded
and remains explicitly recorded. The outer check took 1.18 seconds with its
original 110-second bound; no allowance was added to obtain the pass.
Guarded receipt SHA-256:
`e47dc9b54ca0b7a06a196f6365386039872b432f2035c7081c1ef810d4cfd73b`.
Consolidated source `1c5728b7` subsequently passed the complete 32-chunk offline
lane, both full Python native/no-Rust lanes and all six CI jobs. The exhaustive
per-seed proof above retains its original source and evidence; see the separate
[consolidated CI record](../integration/recovered-review-ci-2026-10-29.md).
