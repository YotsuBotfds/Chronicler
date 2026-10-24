# Left-over persecution fix, 2026-10

Branch `fix/leftover-persecution`, from `integrate/wave-6` at `439f0c5`
(great-person agendas with the preaching fix, historiography, techniques on
by default). Both simulation changes are **corrections**: each changes
behaviour on purpose, fixes one root cause and is its own commit. No
validation threshold, calibration constant or default switch changed.

The defect was found while tracing the agendas' rebellion tail
([great-person-agendas.md](great-person-agendas.md#the-rebellion-tail-fixagenda-preaching)):
82% of hybrid agent rebellions happen in persecuted regions, and half of
the persecuted region-turns have no persecuting ruler.

**Status.**

- Persecution reflects the current ruler and faith every turn. Left-over
  intensity is gone (159 persecuted region-turns per run before, 0.03 after),
  and the agent tick persecutes the people the builder counted.
- Agent rebellions per run (hybrid, 60 worlds, agendas off): 1,355 before,
  1,168 after (−187 ± 84). The reset alone gives 1,078, which is the
  agenda agent's diagnostic number.
- Great-person agendas become rebellion-neutral: on − off moves from
  +176 ± 68 to −15 ± 86 (up/down 13/21).
- Agents-off output is byte-identical to the base. The golden fixtures are
  captured in off mode, so no golden expectation changes (see
  [Golden fixtures](#golden-fixtures)).
- Subset gates on 42-61 and 62-81: PASS, `validation_compare` NO
  REGRESSION; 62-81 passes needs (12 seeds), where the base fails it (11).
- The full gate (200 x 500) waits for the full-gate slot; see
  [Full gate](#full-gate).

## Measurement

Unless stated: hybrid, 200 turns, `--simulate-only`, seeds 42-101 (60
worlds, 26 of them with no agent rebellion in any arm), current defaults,
`PYTHONHASHSEED=0`, one run per arm. Arms run exported trees of `439f0c5`
(base), `2860af0` (reset only) and `44526a1` (branch). Base and reset use
the release build of the `439f0c5` native source (the reset changes no
Rust); the branch uses its own. An output-neutral observer records,
per turn and region, the controller, the ruler's majority faith, the
region's majority belief, the intensity and the belief counts of every
persecuted region. The Rust tick of turn T reads the end-of-turn state of
turn T-1, so an agent event of turn T is classified by the T-1 row:

- **live**: intensity > 0 and the controller's majority faith is militant;
- **left-over**: intensity > 0 and the controller is not militant (or there
  is none);
- **none**: intensity 0.

The base reproduces the agenda agent's numbers exactly (1,355 rebellions;
551 live, 555 left-over, 249 none; with agendas 1,531, +176 ± 68, 20/14).
Differences are paired by seed, ± one standard error.

## Root causes and corrections

### 1. The builder never reset the regions it did not visit (`2860af0`)

`religion.compute_persecution` wrote `persecution_intensity` only for regions
listed by a civ whose majority faith is militant. Every other region kept
its last value. That happens whenever

- a realm's majority leaves a militant faith (16.7 militancy changes per
  run; conversion and schisms move majorities),
- a faith stops being militant,
- a region changes hands (conquest, secession, absorption), or
- a region loses its ruler.

The value then stays until a militant ruler writes the region again, often
for the rest of the run. Half of all persecuted region-turns were left over
(159.0 of 318.3 per run), and 41% of all agent rebellions happened under
left-over intensity (555 per run). Seed 60 is the clean case: Dorrathi, of a
militant faith, conquered a population of another faith; its majority faith
left the militant faith on turn 30, and two regions kept intensities 0.87
and 0.36 for the remaining 170 turns.

The agent tick applies the intensity as if the ruler meant it:

- a satisfaction penalty of 0.09 x intensity;
- rebel utility +0.18 x intensity and migrate utility +0.20 x intensity,
  whatever the agent's satisfaction or loyalty;
- a persecution memory, whose gate only clears at intensity 0;
- no autonomy-need restoration;
- a religious threat packet.

Python reads it too: preaching is blocked (`gp_agendas`), diplomacy books
persecution grievances, schisms take the Stance axis, and martyrdom counts
deaths.

An audit (H9, 2026-04-02) had fixed only the zero-believer case inside
militant-held regions.

**Correction.** The builder owns every region. It clears all intensities,
then writes the militant-held ones from this turn's snapshot. Agent modes
run the builder every turn (the Phase 10 snapshot exists even when it is
empty). Off mode never runs it, so no intensity is ever set there.

**Reset, not decay.** M38b defines the intensity as the ruler's current
policy, set "per region per turn" from the current minority ratio. Its
self-correcting dynamics run through the minority ratio, not through time.
The aftermath of persecution already has its own clocks:

- `martyrdom_boost`: linear decay over 10 turns, the conquest-boost lifecycle;
- the agents' persecution memories: 25-turn half-life (`PERSECUTION_HALF_LIFE`),
  with their own rebel (+0.07) and migrate (+0.17) modifiers. M57 tuned them
  to "damp long-tail rebel escalation from inherited persecution memories".

A decaying intensity would count that aftermath twice. It would also keep
the institutional terms (the penalty, the boosts, the blocked autonomy and
preaching) running under a ruler who persecutes nobody, which is the same
defect at a smaller size. The memory gate and the one-shot "Persecution"
event (the H-14 set filter) both need the intensity to reach 0 so that a
restart counts as new. So the intensity drops to 0.

The native multi-turn check shows the aftermath that remains:

- On the first tick, 30 persecuted agents get persecution memories, and
  their satisfaction is 0.072 below the unpersecuted control (0.09 x 0.8).
- After the reset, no new memories are written and the gap closes to 0.013
  within two ticks; that remainder is the memories.
- A restart writes new memories (63 in total).

**Remaining latency** (by design, the C-12 note in `simulation.py`).

- Phase 9 syncs regions to Rust after Phase 5's conquests. A region
  conquered in turn T therefore carries T-1's persecution for T's tick.
- Phase 10's politics pass (secession, absorption) runs after the builder.
  0.03-0.07 region-turns per run carry a value whose controller changed
  after it was written, and the next Phase 10 resets them.

### 2. The tick persecuted the region's majority, not the ruler's minorities (`44526a1`)

The builder measures the persecuted minority against the militant ruler's
majority faith F: intensity is the share of agents outside F. But the Rust
tick (`satisfaction.rs`, `behavior.rs`, the persecution memory in `tick.rs`)
applied the intensity to every agent outside the region's majority belief M.

When F is itself a local minority, the tick turns persecution around. It
persecutes the ruler's own co-religionists and spares the people the
builder counted. F is a local minority in the common case of a militant
conqueror ruling another faith's people, and there the intensity is
largest (above 0.5).

Evidence on the base, per run:

| | value |
| --- | ---: |
| live persecuted region-turns | 159.3 |
| of which the ruler's faith F is not the region's majority M | 90.6 (57%) |
| agent-turns of the ruler's own faith persecuted there | 658 |
| agent-turns of the other-faith majority spared there | 1,257 |
| rebellions under live persecution | 551 |
| of which by the ruler's co-religionists where F is a local minority | 105 |
| of which by the spared other-faith majority | 105 |

**Intent, per the design docs.** The tick's rule was a simplification:
M38b only says that Rust "reads `agent.belief`, `region.majority_belief`",
which assumes that the ruler's faith is the majority. Everything else in
the design and the code puts the target outside the ruler's faith:

- M38b names the target as "religious minorities" under a militant ruler
  enforcing conformity, and "conquered peoples under hostile empires" as the
  example.
- Detection counts `a.belief != civ.civ_majority_faith`.
- M38b's martyrdom rule is the death of an agent whose "belief differed from
  the civ's majority faith".
- Diplomacy's persecution grievances (`_persecution_inputs`) already treat
  the region's other-faith majority as the persecuted people.

M-AF1 later wrote martyrdom against the region majority, copying the tick's
proxy.

**Correction.**

- `compute_persecution` records the faith it measured against as
  `Region.persecuting_faith`. It is reset together with the intensity, `None`
  while the region is not persecuted, and omitted from serialized output
  while `None`, so off-mode worlds keep their bytes and old saves load (60
  base hybrid states validated).
- The region batch carries it as `persecuting_faith: u8` (255 = none).
- One Rust predicate, `region::persecuted_belief`, decides who is
  persecuted: everyone outside the persecuting faith, never an agent without
  a faith. The satisfaction penalty, the rebel and migrate boosts and the
  persecution memory all use it. The behaviour boosts used to lack the
  no-faith guard that satisfaction has. No faithless agent occurs in a
  persecuted region (0 of 420,944 agent-turns), so that part changes
  nothing.
- A batch without the column falls back to the region majority, the
  earlier rule. The FFI update path keeps intensity and faith as a pair: a
  batch with a new intensity and no faith column resets the faith.
- Martyrdom counts deaths by the same rule.

## Bridge contract

`persecution_intensity` and `persecuting_faith` are persisted per-turn
fields, not one-shot transient signals. Phase 10 rewrites both for every
region, and the next turn's region sync reads them without clearing them,
which `build_region_batch` must not do. Nothing else writes them. Tests:

- `TestPersecutionFollowsCurrentRuler`: a faith leaving militancy, a
  faith's doctrine changing, a region changing hands or losing its ruler,
  a militant conqueror, and a five-turn live → reset → reset → live
  sequence with the one-shot event firing again.
- `TestPersecutionResetReachesTheAgentTick`: six turns through
  `phase_consequences` and `build_region_batch` (the Rust tick's input):
  live, faith lapsed, still clear, live again, region conquered by a calm
  realm, still clear.
- `TestPersecutingFaith`: the recorded faith and its reset, the batch column
  each turn, serialization and old saves, martyrdom under both rules.
- `test_native_tick_persecutes_everyone_outside_the_rulers_faith_across_turns`:
  four native ticks (live, reset, reset, live). It checks who gets
  persecution memories, the satisfaction gap, no new memories while clear,
  and new ones after the restart.
- Rust: `region::tests` (the predicate, including the fallback) and
  `satisfaction::m37_tests::test_persecution_follows_the_rulers_faith_not_the_local_majority`.

Six of the eight reset tests fail on `439f0c5`; the other two (a militant
ruler, a militant conqueror) pin behaviour that is kept. The native test
fails with the `439f0c5` extension.

## Before and after

Agendas off, per run, 60 worlds:

| | base `439f0c5` | reset `2860af0` | branch `44526a1` |
| --- | ---: | ---: | ---: |
| agent rebellions | 1,355 | 1,078 | 1,168 |
| paired against the base | - | −277 ± 84 (up/down 4/27) | −187 ± 84 (13/21) |
| share in persecuted regions (pooled) | 81.6% (live 40.6, left-over 41.0) | 54.4% (live) | 55.3% (live) |
| persecuted region-turns: live / left-over | 159.3 / 159.0 | 156.6 / 0.05 | 157.0 / 0.03 |
| agent-turns persecuted by the tick: live / left-over | 2,269 / 2,235 | 2,350 / 1 | 3,097 / 1 |
| of the live ones: ruler's own faith / other-faith majority spared | 658 / 1,257 | 616 / 1,173 | 0 / 0 |
| migrations (agent events) | 1,825 | 1,821 | 1,898 |
| share of migrations in persecuted regions | 34.6% | 19.8% | 21.1% |
| conversions (belief changes between Phase 10 snapshots) | 660 | 576 | 616 |
| schisms | 12.0 | 12.0 | 12.0 |
| realm militancy changes | 16.7 | 12.4 | 14.4 |
| one-shot Persecution events | 5.3 | 13.9 | 15.4 |
| Mass Migration events | 17.6 | 14.1 | 15.6 |
| polities alive at turn 200 | 2.97 | 2.97 | 2.92 |

From the subset gates (20 worlds x 200 turns per set):

| | base | reset | branch |
| --- | ---: | ---: | ---: |
| migration per agent-turn, 42-61 / 62-81 | 0.0577 / 0.0474 | 0.0567 / 0.0468 | 0.0580 / 0.0474 |
| rebellion per agent-turn, 42-61 / 62-81 | 0.0428 / 0.0222 | 0.0322 / 0.0187 | 0.0352 / 0.0186 |
| polities alive, 42-61 / 62-81 | 3.15 / 2.95 | 3.05 / 3.00 | 3.00 / 2.90 |

Notes:

- **Where the rebellions went.** In the base, 41% of rebellions sat under
  left-over intensity. After the reset, about half of those happen anyway,
  in regions now at intensity 0 ("none" rises from 249 to 491). Those agents
  still carry the memories, the low satisfaction and the grievances of the
  persecution that did happen. The other half are gone.
- **Correction 2 adds back +90 ± 98** (up/down 18/16; not significant)
  against the reset alone. The tick now persecutes 3,097 agent-turns per run
  instead of 2,350, mostly the conquered other-faith majorities it used to
  spare.
- **Migration.** Correction 2 raises migration: total migrations +4% on the
  base, and live-persecution migrations from 322 to 401. That sits on the
  tightest required margin of the full gate (0.0512 against the 0.05 floor
  on the techniques-default full gate). The reset alone moves the total by
  −0.2%.
- **Schisms** saturate the faith registry (`MAX_FAITHS` = 16) in every world
  by turn 9 (12 per run, the 12th on turn 8.8 on average, in every arm), so
  they cannot respond to persecution after that. This was already so before
  the fix; see "Open items".
- **The one-shot Persecution event** now fires again when persecution
  restarts in a region: the H-14 filter clears a region once its intensity
  is 0, which left-over values prevented. That gives more importance-6
  events, about 10 per run.
- **Seed 60.** Off: 1,251 → 516 (reset) → 1,083 (branch). On: 2,504
  (1,306 of them under left-over intensity) → 1,125 → 2,285. On the branch
  all of seed 60's persecution is live, by a militant ruler of its
  conquered regions (226 region-turns against 150 with agendas off).

## Great-person agendas, re-measured

Same 60 worlds, `--gp-agendas` against the switch off of the same tree:

| Per run | base `439f0c5` | reset `2860af0` | branch `44526a1` |
| --- | ---: | ---: | ---: |
| rebellions, off / on | 1,355 / 1,531 | 1,078 / 1,054 | 1,168 / 1,154 |
| on − off | +176 ± 68 | −24 ± 80 | −15 ± 86 |
| seeds up / down | 20 / 14 | 17 / 17 | 13 / 21 |
| median seed ratio (34 worlds with any) | 1.06 | 1.01 | 0.91 |
| worlds that double by > 1,000 | 60, 93, 99 | 48, 61, 93, 97 (101 halves) | 60, 61, 73, 93 |
| worst seed | 99: 310 → 3,037 | 95: 1,465 → 2,788 | 73: 688 → 2,640 |
| rebellions under left-over intensity, off / on | 555 / 742 | 0 / 0 | 0 / 0 |
| conversions, off / on | 660 / 734 | 576 / 575 | 616 / 603 |

By seed set, branch on − off:

- 42-61: +114 ± 144 (6/6);
- 62-81: +101 ± 148 (3/4);
- 82-101: −259 ± 145 (4/11).

Agendas are rebellion-neutral on the branch. What remains is the chance
tails the agenda agent measured under its reset diagnostic: with no mean
effect, about 4 of 60 worlds still double by over 1,000. The reset arm
reproduces that diagnostic exactly (1,079 / 1,054, −24 ± 80, 17/17).

## Subset gates

20 worlds x 200 turns, hybrid, `--parallel 2`, current defaults. Each tree
ran its own exported scripts and native build; the branch and the reset
are compared against the base report with `chronicler.validation_compare`.
In the subset only community, needs and cohort are required.

| Oracle | 42-61 base / reset / branch | 62-81 base / reset / branch |
| --- | --- | --- |
| gate | PASS / PASS / PASS | **FAIL** (needs) / **FAIL** (needs) / PASS |
| comparator | - / NO REGRESSION / NO REGRESSION | - / NO REGRESSION / NO REGRESSION (resolves needs) |
| community (15 required) | 20 / 20 / 20 | 20 / 20 / 20 |
| needs (12 required; median effect) | 17, 1.00 / 17, 1.00 / 15, 0.72 | **11**, 0.32 / **11**, 0.32 / 12, 0.65 |
| cohort (seeds; median effect) | 20, 1.25 / 20, 1.08 / 20, 1.11 | 20, 1.36 / 20, 1.38 / 20, 1.35 |
| era (seeds with inflections; silent) | 20; 0 / 20; 0 / 20; 0 | 20; 0 / 20; 0 / 20; 0 |
| arcs (seeds with three types; families) | 15; 5 / 17; 5 / 19; 6 | 18; 6 / 15; 6 / 15; 6 |
| artifacts (status; creation; loss) | PARTIAL 2.13, 2.6% / PARTIAL 2.21, 3.1% / PARTIAL 2.16, 3.8% | PASS 2.29, 2.2% / PARTIAL 2.29, 0.8% / PARTIAL 2.30, 1.4% |
| regression | FAIL (`civ_survival`) / FAIL (`civ_survival`) / PASS (strict) | PASS (calibrated: migration) / FAIL (rebellion, migration, `civ_survival`) / FAIL (rebellion, migration) |
| satisfaction mean; latest | 0.580; 0.597 / 0.588; 0.610 / 0.589; 0.607 | 0.599; 0.604 / 0.603; 0.611 / 0.601; 0.611 |
| migration per agent-turn | 0.0577 / 0.0567 / 0.0580 | 0.0474 / 0.0468 / 0.0474 |
| rebellion per agent-turn | 0.0428 / 0.0322 / 0.0352 | 0.0222 / 0.0187 / 0.0186 |
| all founders surviving (limit 0.20) | 0.25 / 0.25 / 0.20 | 0.20 / 0.25 / 0.20 |
| extinct worlds | 0 / 0 / 0 | 0 / 0 / 0 |
| final population min, median, max | 70, 157.5, 285 / 50, 154.5, 271 / 79, 157, 247 | 76, 173.5, 283 / 76, 171.5, 283 / 76, 163, 283 |

The base gates reproduce the agenda agent's `b7d9ced` base gates exactly:
historiography is observational, and the agenda fix is identity with the
switch off.

- **62-81 needs** is the known techniques-on one-seed miss
  (`techniques-default.md`); the branch reaches 12 seeds.
- **Rebellion floor on 62-81** (informational in the subset). The
  regression oracle asks for 0.02-0.08 rebellions per agent-turn. Eleven of
  these 20 worlds have no agent rebellion, and the set falls from 0.0222 to
  0.0186. On the full profile the techniques-default rate was 0.0503; a 15-20%
  fall keeps it far above the floor. The full gate decides.
- **Migration on 62-81** stays at the calibrated floor (0.0474, base 0.0474).

## Golden fixtures

No golden expectation changes. The live oracles
(`tests/fixtures/performance/corrected_*` and the artifact fixtures read by
`tests/test_governance_dormancy.py` and `tests/test_historiography.py`) are
captured in off mode with the native ecology and politics runtimes
disabled. Off mode never runs the persecution builder, and
`persecuting_faith` is omitted while `None`. `test_performance_equivalence`
and `test_governance_dormancy` pass unchanged on the branch.

Agents-off identity, base against branch, each with its own native build:
seeds 42 and 7, 150 turns, `--simulate-only`, `PYTHONHASHSEED=0`, compared
with `scripts/diplomacy_identity.py compare`: 16 files, **0 differences**.

The roll-forward on top of the food-logistics fixtures is recorded in
[Full gate](#full-gate).

## Tests changed and why

- **Added** (Python): `TestPersecutionFollowsCurrentRuler` (7),
  `TestPersecutionResetReachesTheAgentTick` (1), `TestPersecutingFaith` (6)
  and the native multi-turn test (1), all in `tests/test_persecution.py`.
- **Added** (Rust): 2 in `region::tests`, 1 in `satisfaction::m37_tests`.
- **Changed** (Rust): every `SatisfactionInputs` literal in
  `satisfaction.rs`, `tests/test_memory.rs`, `tests/satisfaction_m38a.rs` and
  `tests/test_urban.rs` gains `persecuting_faith: 0xFF`, which is the
  earlier rule. No expected value changes.
- **Changed** (Python, `569040d`, following from correction 2):
  `tests/test_maritime.py::test_hybrid_merchants_cross_sea_lanes_and_are_raided_deterministically`
  runs seed 12 instead of seed 7. It needs a procedural hybrid world where
  merchants cross sea lanes and lose cargo to pirates within 40 turns.
  Seed 7's history changes with the corrected tick and its sea trade nearly
  vanishes (86 crossings and 3 cargo lost on the base, 6 and 0 on the
  branch). Seed 12 gives 295 / 11 on the base and 291 / 5 on the branch.
  The assertions are unchanged. Over 40 turns the reset alone leaves seeds
  7-12 identical to the base.
- No other Python expectation changes.

## Verification

Linux, Python 3.13, native extension built fresh (`maturin develop
--release`) and verified as the compiled `chronicler_agents.chronicler_agents`
with real `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`
classes.

Before the merge with food logistics:

| Check | Result |
| --- | --- |
| `cargo test --locked` (`569040d`) | 897 passed, 0 failed, 2 ignored (3 new) |
| `pytest -m "not slow" -n 2` (`569040d`) | 5,902 passed, 3 skipped, 526 subtests. On `44526a1`: 5,901 passed, 1 failed (the maritime test, see above), 3 skipped. `439f0c5` collects 5,890, the branch 5,905 (15 new) |
| `pytest -m slow -n 2` (`44526a1`) | 11 passed, 3 skipped |
| no-Rust lane (fresh virtualenv without `chronicler_agents`, slow included; `44526a1`) | 5,701 passed, 204 skipped |
| `scripts/run_python_oracle_checks.py` (PR #19's guard fix applied locally, not committed; `44526a1`) | PASS: 1,892 passed, 10 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O; pytest 72.6 s of the 110 s limit (75 s wall) |

The slow, no-Rust and oracle lanes ran before `569040d`, which changes only
a native-only test (skipped in the no-Rust and oracle lanes; not slow).

## Full gate

Waiting for the full-gate slot (`fix/food-logistics` holds it and rolls the
golden fixtures forward). After food logistics lands in `integrate/wave-6`,
this branch merges `origin/integrate/wave-6` (no rebase), rolls the
fixtures forward with provenance if anything changes, and runs the 200 x 500
gate against the then-current defaults' full report.

## Open items

- **The full gate** (above).
- **Schisms saturate** the 16-faith registry by turn 9 in every world, so
  later persecution, clergy dominance or conquest cannot split a faith.
  This predates the fix and is a calibration question for the religion
  owners.
- **Chance tails** remain: any change of history can carry a world into a
  persecuted conquest. Under the branch about 4 of 60 worlds double their
  rebellions by over 1,000 between two arms with no mean difference.
- **Region-level consumers.** The autonomy need, threat packets and the
  persecution-memory gate read "this region is persecuted", not "this agent
  is". The ruler's co-religionists in a persecuted region therefore still
  lose autonomy restoration. That is consistent with the design (life under
  a persecuting regime) and is unchanged.
- **Martyrdom's conversion target** is the region's dominant foreign priest
  faith, not necessarily the persecuted faith (unchanged).
