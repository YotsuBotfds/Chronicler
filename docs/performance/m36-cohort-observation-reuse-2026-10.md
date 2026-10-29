# Draft M36 cohort observation reuse — 2026-10-29

Status: source-only inactive draft. Base source is `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`.
No test, world, benchmark or native build has run for this draft during the
forkserver timing window. Production source and scientific gates are unchanged.

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

Those are source findings, not observed repeated-cohort parity. Dynamic alias,
repeat-order and environment behavior still require validation before adoption.
The draft makes no claim that original repetitions have already been observed
to produce the same per-seed outcomes.

## Draft change

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
loop computed, conditional on the repeated-cohort equivalence still to verify.
Three pure parameterized cases cover exact seed/horizon/argument requests,
retained ordering/duplicates, no world/event alias after copying and immutable
observations. These contracts are also unrun at draft creation.

This changes test setup reuse, not the scientific population gate's samples,
windows or policy. It is not an optimization of production simulation physics
and establishes no wall-time improvement.

## Required validation after timing release

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
