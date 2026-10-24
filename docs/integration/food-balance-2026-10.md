# Food balance, 2026-10

Branch `fix/food-balance`, based on `integrate/wave-2` at `db26681` (PR #18).
Corrections 1-9 below are **corrections**: each changes behavior on purpose,
fixes one root cause, and is its own commit. Correction 10 is a separate,
documented **recalibration** of one satisfaction constant that had been cut to
compensate for the starving worlds. The golden oracles are rolled forward with
per-correction provenance; older fixtures stay frozen. No famine threshold,
food demand constant or validation threshold changed.

At `db26681` hybrid template worlds were chronically underfed and famine was
a steady state, not an event:

- 58% of populated region-turns ran below 0.2 food sufficiency and 4% at or
  above 1.0 (ten seeds, 200 turns; 62% and 2.5% over 500 turns).
- Harvests covered demand in 3% of region-turns, and 1% of region-turns kept
  half a turn of food after eating.
- About 750 famine events per 500-turn run: every populated region was in
  famine on every 5-turn cooldown.
- Mutual aid never sent a convoy. Populations sat at 1.0-1.35x capacity, and
  "Region N pop P exceeds 2x capacity" warnings fired 220 times in the
  subset gate.
- 64-region / 16-civ procedural hybrid worlds lost over 90% of their people:
  seeds 7-10 fell from 822 to 64 on average by turn 150.

**Status.**

- Hybrid template worlds have a real food economy: 42% of region-turns are
  fed (sufficiency at least 1), a third of harvests cover demand, and famine
  events per 500-turn run fall from 752 to 341, from saturation to about two
  thirds of it. Famine is most frequent in winter (plains short in two thirds
  of winter turns, about half of the others), in drought and cooling phases,
  and in regions without a food resource; it is still far from rare (see
  "Open items").
- Procedural 64-region worlds no longer collapse: seeds 7-10 grow from 817 to
  988 on average over 300 turns.
- Mutual aid is alive: 12 convoys per 200-turn template run, 22 per 500
  turns, and 46 per 300-turn procedural run (0 before).
- Gates: see "Gate results" (subset and full 200 × 500, 0 of 200 worlds
  extinct).
- Open items are listed at the end.

## Root causes and corrections

The order is the commit order. Template measurements use the default
8-region / 4-civ world (`--agents hybrid`, seeds 42-51, 200 turns) unless
stated.

### 1. Aggregate overflow migration ran on agent-owned populations (hybrid)

`climate.process_migration` clamps each overflowing region to its effective
capacity and pushes the "surplus" onto neighbours. It ran in every agent
mode, but in hybrid and demographics-only modes the native pool owns
population: no agent moved, and the write-back restored the real counts at
the end of the turn. For phases 2-9, though, ecology pressure, the soil and
disease gates, plague crowding and stockpile caps read the fictitious
numbers (seed 43, turn 40: aggregate `[64, 3, 15, …]` against agent counts
`[129, 25, 2, …]`), and the turn emitted migration/starvation events and
receiving-civ stability penalties for moves that never happened (105 such
migrations in a 200-turn run). The extinction fix noted the clamp and left it
in place.

**Correction.** The pass is a no-op in hybrid and demographics-only modes.
Off and shadow modes, where Python owns population, are unchanged.

### 2. Soil degraded against the degraded capacity (ratchet)

Soil degraded whenever population exceeded `effective_capacity`, which
already contains the degraded soil and the drought-depressed water. A single
drought started a ratchet: lower soil lowered the threshold, the region
degraded further, and recovery (since the extinction fix, population below
0.75 × potential capacity) never came while the region was populated.

**Correction.** Degradation compares population with the undegraded potential
capacity (`carrying_capacity × capacity_modifier`), the reference recovery
already uses. Python `ecology._tick_soil`, Rust `tick_soil_controlled` and the
legacy parity oracle change together.

### 3. Temperate water recovery was population-gated

Temperate recovery was multiplied by the population pressure multiplier while
the drought and cooling losses were not. Over one 75-turn climate cycle the
losses (15 × 0.04 + 15 × 0.02 = 0.9) equal the temperate gain (30 × 0.03) only
at multiplier 1, an empty region. Every populated region lost water each
cycle; one at capacity (multiplier 0.1) recovered 0.09 of the 0.6 a drought
takes and sat at the 0.1 floor. Crop yields are soil × water, so this alone
held grain plains near zero.

**Correction.** Recovery is the plain climatic rate in the controlled and
uncontrolled paths (Python, Rust and the parity oracle). The irrigation bonus
keeps its pressure gate.

### 4. Mines were built on farmland

`valid_build_types` offered MINES everywhere, so trait build priorities put a
mine on almost every region by mid-game, grain plains included. A mine costs
its region 0.03 soil per turn and yields nothing without a mineral resource;
the M15 design has mines prioritise mineral regions.

**Correction.** MINES are valid only where a resource slot is ORE or PRECIOUS.
Existing mines in saved worlds are untouched.

### 5. Travelling merchants were missing from the occupational balance (native)

M58a excludes Loading and Transit merchants from every region aggregate, so
their position cannot leak into the regions they cross. A trading merchant is
Loading or in Transit from the turn it plans a trip until it arrives, which
covers almost every decision phase, so the occupational supply that drives
switching left out most of a region's merchants. Idle agents kept switching
into trade while the travellers could not switch out. Seed 43 ran at a median
44% merchants against a 4.3% target and 35% farmers against 66%, with 532
farmer-to-merchant switches against 139 back.

**Correction.** `behavior::compute_region_stats` and
`tick::compute_satisfaction_region_inputs` add on-trip merchants to the
occupational supply and occupational population of their trip origin, the
anchor the M58a economy tally already uses. They still take no decisions and
stay out of satisfaction, rebellion, civ and overcrowding aggregates.

### 6. Merchants settled wherever they delivered (native)

A merchant that completed a trip stayed at the destination. Every delivery
permanently moved one person, and one mouth, from the exporter to the
importer, split households, and left the exporter short of merchants, which
it re-recruited from its farmers. With correction 5 in place, seed 43 still
ran at a mean 29% merchants against a 7% target and 48% farmers against 61%;
only about a third of the merchants were on a trip at any time.

**Correction.** Arrivals record their trip origin (`AgentPool::trip_home_region`,
a per-turn transient). They stay at the market through the 0.95 knowledge
phase, so an arrival still observes the destination (M59a), do not plan a
trip from there, and `merchant::return_delivering_merchants_home` sends them
home right after it. They plan from home the next turn. The return leg is not
simulated, so outbound trip times are unchanged. The mobility phase clears the
previous turn's arrival flags and pending returns first.

With every other correction applied, seed 43 runs at 18% merchants against an
11% target and 51% farmers against 59%; over ten template worlds famine events
fall from 195 to 145 per 200-turn run and fed region-turns rise from 35% to
43% (measured before correction 10, which leaves them about the same).

### 7. The fertility crowding brake sat inside the soil-degradation band (native)

Births tapered from 1.0x capacity and stopped at 1.6x. That band was chosen
while the ecology read populations clamped by correction 1's migration pass,
so its interaction with the soil model was invisible. The ecology degrades
soil above potential capacity and recovers it only below 0.75x; a brake that
starts at 1.0x parks every region in the degradation band (hybrid median
population/capacity 1.0 against 0.42 in off mode). With real populations
visible, grain plains fell to soil 0.65 within 200 turns and kept falling.

**Correction.** Births taper from 0.75x and stop at 1.0x capacity, the band in
which the land neither degrades nor needs to recover. Mortality crowding
stress is unchanged (it starts at 1.0x). `fertility_rate`, the test
convenience without a pressure argument, now means "uncrowded" (pressure 0.0).

### 8. The goods economy read the harvest index as goods (PR #11 unit regression)

The goods economy produces yield × farmer labour and feeds 0.5 per head.
Since the ecology/goods integration (PR #11, `76e1d2a`) the yield it reads is
the M34 realized harvest index: base × season × climate × ecology (crops soil
× water, forestry forest cover) × reserve ramp. That index is a multiplier
around the base, not an amount of goods. Its long-run mean on healthy default
plains is 0.95 (season) × 0.82 (climate cycle) × 0.54 (soil 0.9 × water 0.6) =
0.42 of the base, so a farmer averaged 0.42 grain on pristine land (realized
template plains mean 0.239 against base about 1.04; fish 0.775). Even
untouched plains were at best break-even.

**Correction.** `ecology.goods_per_worker` divides the index by its derived
long-run normal, `harvest_normal_index` (season mean × phase-share-weighted
climate mean × the terrain-default ecology for crops and forestry, 1
otherwise). Healthy land averages exactly the base yield over a full cycle;
season, climate, degradation, suspension and depletion still move output. The
conversion is applied where the economy reads yields
(`fisheries.economy_yield`), to the fishery catch budget, and to the fishery
labour split. The ecology, the stock model, the aggregate famine-yield check
and the stored indices are unchanged, so saves and bundles keep their meaning.
There is no tuning key: the normal is computed from the model tables.

### 9. Plague contagion grew with world connectivity (procedural collapse)

An outbreak excited plague hazard in every contacted civ by
`PLAGUE_CONTACT_ALPHA × contact weight`, however many contacts the infected
civ had. The decaying hazards were calibrated on the default four-civ
template, where a civ's total contact weight averages 3.0 (seeds 42-43). In
64-region / 16-civ procedural worlds it averages 5.4 (p90 10); the plague
branching ratio exceeded 1 and outbreaks hit 4-9 civs a turn. Clean
ablation, every other correction applied: procedural seeds 7 and 8 still fall
from 758 and 840 people to 68 and 74 by turn 150 (about 280 plague events in
300 turns); with the correction they hold 928 and 984 (about 135).

**Correction.** An outbreak spreads at most `PLAGUE_CONTACT_WEIGHT_REF = 3.0`
of contact weight at full strength; a civ with more contact divides it in
proportion to weight. Within the reference weight, which covers the template
worlds, nothing changes.

### 10. Recalibration: food-shortage satisfaction weight (native)

This is a recalibration, kept in its own commit. `FOOD_SHORTAGE_WEIGHT`
multiplies an agent's regional food shortfall into a satisfaction penalty.
M42 set it to 0.30; M47c halved it to 0.15 so the uncapped penalty on top of
the 0.40 social cap was not too harsh early on. Three later cuts, to 0.10 (M53
baseline capture: "should not zero out recovering survivor cohorts"), 0.08
(M55: "easing the branch-wide satisfaction dip") and 0.07 (M54+M55 closeout:
"avoiding the late-run satisfaction floor miss"), were made to recover the
regression satisfaction floor on worlds that starved every turn and died (the
M53 baseline records agent extinction at turn 77 on average).

With corrections 1-9 the cuts overshoot. The first full gate on the corrected
branch failed only regression `latest_satisfaction_mean`: 0.6502 against the
unchanged 0.65 ceiling (mean 0.620; rebellion 0.053 and migration 0.055
inside their bands; all-initial-civ survival 0.15; 0 of 200 worlds extinct).
Fed agents now also gain from healthy soil and water and from higher civ
stability, which famine no longer drains every turn.

**Recalibration.** The floor-recovery cuts are undone and the weight returns
to the M47c value 0.15. The validation ceiling is unchanged. The weight is
not raised back to the M42 0.30: M47c's halving had its own design reason.
With 0.15 the full gate passes strictly (satisfaction 0.594, latest 0.643,
rebellion 0.053, migration 0.056); the food-economy measurements barely move
(fed region-turns 42.7% → 42.3%, famine 145 → 150 per 200-turn run).

Determinism: no new random draws. Stat changes keep their accumulator
categories; regions and civs are identified by index; the new native
transient (`trip_home_region`) is set and consumed within one tick and
cleared at the start of the next mobility phase.

## Before and after

`db26681` against the branch head, hybrid. Template: 8 regions / 4 civs.
Sufficiency is the economy's pre-consumption food / demand, clamped to
[0, 2], over populated controlled region-turns.

| Measure | Before | After |
| --- | --- | --- |
| Region-turns analysed (10 × 200) | 13,758 | 10,443 |
| Sufficiency p10 / p25 / median / p75 / p90 | 0 / 0 / 0.10 / 0.49 / 0.81 | 0 / 0.20 / 0.80 / 1.70 / 2.0 |
| Share below 0.2 / below 0.5 | 58.5% / 75.6% | 24.9% / 38.0% |
| Share fed (at least 1.0) | 4.3% | 42.3% |
| Harvest covers demand (regions in surplus) | 3.0% | 31.9% |
| Keeps half a turn of food after eating | 1.1% | 28.0% |
| Famine events per 200-turn run | 296 | 150 |
| Famine events per 500-turn run (seeds 42-45) | 752 | 341 |
| Famine per populated region-turn, 500 turns (0.2 = continuous) | 0.21 | 0.14 |
| Mutual-aid convoys per 200-turn / 500-turn run | 0 / 0 | 12.2 / 22 |
| Population / capacity, median (p90) | 1.00 (1.35) | 0.66 (1.00) |
| Population / effective capacity, median | 2.37 | 1.08 |
| Plains soil / water, median | 0.66 / 0.58 | 0.95 / 0.69 |
| Population at turn 200, mean (min) | 374 (275) | 185 (141) |
| Population at turn 500, mean (min) | 455 (378) | 190 (156) |
| Civs alive at turn 200 | 3.0 | 2.9 |
| "exceeds 2x capacity" warnings, subset gate | 220 | 1 |

Median sufficiency by terrain (200 turns): plains 0.10 → 0.93, coast
0.79 → 1.09, desert 0.35 → 0.50, mountains 0 → 0.13, tundra 0.08 → 0.30.
Famine events per 200-turn run by terrain: plains 135 → 74, mountains 67 → 35,
coast 42 → 23, desert 34 → 14, tundra 16 → 2, forest 3 → 3. By climate phase:
temperate 128 → 58, warming 63 → 23, drought 55 → 35, cooling 50 → 34.

The population is lower because the brake (correction 7) now holds regions
inside the band the ecology can sustain instead of at 1.0-1.35x capacity on
degrading land. It is stable over 500 turns (seeds 42-45: 201 at turn 0, 190
at turn 500, minimum 123-134). Fewer region-turns are analysed because people
no longer pile into regions without food: before, merchant relocation
(correction 6) and the fictitious migration (correction 1) kept mountains,
deserts and forests populated beyond what imports could feed.

Off mode (template, 10 × 200; soil, water, mines and plague apply there):
famine events per run 140 → 122, median population/capacity 0.42 → 0.50.

Procedural 64 regions / 16 civs, seeds 7-10, 300 turns:

| Measure | Before | After |
| --- | --- | --- |
| Population turn 0 / 75 / 150 / 225 / 299 (mean) | 822 / 320 / 64 / 56 / 70 | 817 / 880 / 893 / 955 / 988 |
| Final population per seed (7, 8, 9, 10) | 60, 91, 55, 75 | 1038, 1000, 915, 997 |
| Lowest population, any turn | 43-59 | 726-828 (at most 14% below a seed's start) |
| Plague events per run | 281-286 | 122-144 |
| Share fed / median sufficiency | 11.4% / 0.34 | 45.6% / 0.88 |
| Mutual-aid convoys per run | 0 | 46 |
| Famine per populated region-turn | 0.22 | 0.15 |
| Civs alive at the end (mean) | 22.3 | 17.0 |

Before, the many surviving civs are fragments of a collapsed world.

## Golden fixtures

New live oracles, captured with the tests' own capture loops (off mode, native
ecology/politics disabled): `tests/fixtures/performance/corrected_food_balance_2026_10.json`
and `corrected_artifacts_food_balance_2026_10.json`. `corrected_extinction_2026_10*`
and older fixtures are frozen. `tests/test_performance_equivalence.py` adds the
`food_balance` link to `ORACLE_CHAIN` (extinction → food balance), and
`tests/test_governance_dormancy.py` reads the new files.

Each correction's provenance entry lists the first changed turn index of each
workload relative to the oracle with all earlier corrections applied
(consecutive captures of the branch commits):

| Correction | single | standard | wide | Artifact files changed |
| --- | --- | --- | --- | --- |
| FB-MIGRATION | — | — | — | none (agent-owned modes only) |
| FB-SOIL | 9 | 18 | 0 | state, bundle; memories (standard, wide) |
| FB-WATER | 0 | 0 | 0 | bundle; state (wide) |
| FB-MINES | — | 15 | 22 | state, bundle, memories |
| FB-MERCHANT-OCCUPATION | — | — | — | none (native only) |
| FB-MERCHANT-HOME | — | — | — | none (native only) |
| FB-CROWDING-BRAKE | — | — | — | none (native only) |
| FB-GOODS-UNITS | — | — | — | none (the off-mode lane's outcomes do not read the converted yields) |
| FB-PLAGUE-CONTACT | — | — | 35 | state, bundle, memories |

The recalibration (correction 10) is native only and leaves the oracles
unchanged. The capture tool reproduced the frozen extinction oracle exactly
(turn hashes, RNG traces and artifact bytes) at `db26681` before any
correction.

## Tests changed and why

New tests:

- `tests/test_food_balance.py` (21 cases): migration no-op in hybrid and
  demographics-only and unchanged in off/shadow/None; soil below potential
  does not degrade, above it does; temperate water recovery independent of
  population and a populated region recovering its water over a climate
  cycle; mines invalid without ORE/PRECIOUS and valid with either;
  `harvest_normal_index` derived from the M34 tables; healthy land averaging
  exactly the base yield over four climate cycles; `goods_per_worker` on
  empty and zero slots; `economy_yield` and `catch_budget` in goods units;
  plague contagion unchanged within the reference weight and shared across
  12 contacts with a bounded total.
- Rust `ecology.rs`: degraded soil below potential does not degrade;
  temperate recovery independent of population (controlled and
  uncontrolled).
- Rust `behavior.rs`: Loading and Transit merchants count in their origin's
  occupational supply and demand, not in the region they are in, and stay out
  of the civ aggregates.
- Rust `tests/test_merchant.rs`: a delivering merchant stays at the market for
  the arrival turn, does not plan there, returns home, and plans from home
  next turn; a pending return is cleared by the next mobility phase.
- Rust `satisfaction.rs`: the food-shortage penalty is `shortfall × 0.15`.

Changed expectations, each following from the corrections:

- Unit conversions (correction 8). These tests built economy inputs from
  index values or compared economy inputs with stored indices; they now state
  goods explicitly (`goods × harvest_normal_index`) or compare in goods units,
  so they exercise the same physical scenarios:
  - `test_economy_bridge.py::test_region_input_batch_values`: the batch
    yield is `goods_per_worker(GRAIN, 1.5)` (was 1.5).
  - `test_economy_coupling.py::test_secondary_salt_and_precious_reach_real_stockpiles`:
    fixture indices scaled so the slots are still worth 2 salt and 3
    precious per farmer.
  - `test_economy_coupling.py::test_ffi_transmits_realized_all_slot_yields_not_potential`:
    the batch carries the realized index in goods units.
  - `test_economy_m43a.py::test_food_sufficiency_backward_compat_full_path`:
    fixture index is `demand/pop × harvest_normal_index(GRAIN)`.
  - `test_fishery_experiment.py`: `economy_yield` and the first batch yield
    are goods (`goods_per_worker(FISH, 1.0)`, upper bound likewise); the
    stock-debit and native-budget tests read the budget through
    `catch_budget`; the per-slot cap fixture is scaled.
  - `test_fishery_recovery_validation.py::test_saved_disabled_memory_is_ignored_then_removed_slot_resets`:
    the saved credit is `goods_per_worker(FISH, 40)` (was 40).
  - `test_fisheries_mutual_aid_promotion.py::test_hybrid_resume_continues_the_fishery_from_its_saved_state`:
    the resumed catch credit is compared in goods units.
  - Scripts that build economy fixtures state goods explicitly:
    `scripts/economy_coupling_experiment.py` (valley 1.8 grain, coast 4.0
    fish per farmer), `scripts/mutual_aid_adversarial.py` (prescribed crops),
    `scripts/validate_fishery_recovery.py` and `scripts/qualify_third_wave.py`
    (expected production and budget checks in goods). Each falls back to the
    old meaning when run against a source without `harvest_normal_index`.
- Rust `tests/test_ecology.rs`: `test_basic_plains_tick` water 0.615 → 0.63
  (correction 3); `test_soil_degradation_mult_from_streak` population 55 → 65,
  above the potential capacity of 60 (correction 2).
- Rust `demographics.rs` (correction 7): the soft-start test probes just
  below the new soft start (0.70, was 0.95); the strong-suppression test
  uses pressure 0.9 inside the new band (was 1.4); the satisfaction-gate
  ramp test runs uncrowded (pressure 0.0, was 1.0).
- Golden oracles: see "Golden fixtures".
- Emergent mutual-aid trajectories (native, multi-turn):
  - `test_mutual_aid_adversarial.py`: one convoy now lifts the Mine over the
    stress threshold, so a funded episode is a single send at turn 4 (was
    sends at turns 4 and 5), the "exhausted" control uses treasury 1 (was 2,
    one send's cost), and each fresh three-turn stress reactivates aid, at
    turns 10 and 14 (was one reactivation at 14). The streak still resets to
    0 at recovery and must be reacquired as 1, 2, 3; the exhausted run still
    sends nothing after its first convoy.
  - `test_third_wave_joint.py::test_joint_full_turn_accounting_and_determinism`
    and `test_mutual_aid_long_cargo.py::test_long_cargo_independent_per_good_conservation_and_once_only_settlement`:
    the donor set was `{A, B}`; it is now required to contain A and be a
    subset of `{A, B}`, because A's free surplus alone covers both recipients
    in some runs. Multi-donor sharing stays pinned exactly by the
    hand-calculated `test_multiple_donors_competing_recipients_caps_and_exhaustion`.

No validation threshold changed. At `db26681` the subset failed regression
`civ_survival` (all-initial-civ survival 0.25 against a limit of 0.20, an M53
design target: "0 or all 4 civs surviving in more than 20% of seeds"); on the
branch head it is 0.15 in the subset and 0.165 in the full profile. Before
correction 10 the branch subset also sat at 0.25, which shows how close to
run-to-run noise this band is.

## Verification

All on the branch head, Linux, Python 3.13, with the native extension rebuilt
from this tree (`maturin develop --release` at `6cd3fcb`, the last commit that
touches `chronicler-agents`; the installed
`chronicler_agents.chronicler_agents` module, SHA-256 `e38fbfde…e3b26f`, was
built after the last Rust source change and exposes `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator`).

- `pytest -m "not slow" -n 2`: 5,519 passed, 3 skipped (base 5,497 passed,
  3 skipped; new: 21 food-balance cases and the `food_balance` oracle-chain
  link).
- Slow tests (`-m slow`): 9 passed, 3 skipped (two placeholder skips, one
  data skip in the M36 invest-culture check).
- No-Rust environment (fresh venv without `chronicler_agents`, same
  selection): 5,321 passed, 187 skipped.
- `cargo test --release` in `chronicler-agents`: 888 passed, 0 failed, 2
  ignored.
- Offline Python oracle lane (`scripts/run_python_oracle_checks.py` test
  list, without `-x`): 1,569 passed and the same 28
  `test_checkpoint_replay.py` failures as at `db26681` (1,568 passed). On
  Linux `platform.platform()` in checkpoint identity spawns `uname`, which the
  lane's guard forbids; this is environmental and pre-existing.

## Gate results

Both gates ran on the branch head with `--parallel 2` and the `db26681`
subset report as the comparison baseline. Only the report files are kept,
outside the repository.

### Full (200 seeds × 500 turns, hybrid)

**PASS, strict adjudication: every required oracle passes.**
`validation_compare` reports **NO REGRESSION**, with regression and
artifacts resolved against the subset baseline's oracle set.

| Oracle | Result |
| --- | --- |
| regression | PASS, strict. 0 of 200 worlds extinct; final population 33 / 182 / 325 (min / median / max). Satisfaction 0.594, latest 0.643 (ceiling 0.65), std 0.182. Migration 0.0556, rebellion 0.0529. Occupation violations 0.14%. All-initial-civ survival 0.165 (limit 0.20). Gini in range 85%. |
| artifacts | PASS, strict. Creation 1.10 per civ per 100 turns. Loss/destruction 3.8% (40 lost, 127 destroyed, 4,394 artifacts). |
| arcs | PASS. All 6 families; 161 seeds with three types. |
| era / needs / cohort / community | PASS. 200 of 200 seeds with inflections and 1 silent collapse; expected sign in 190; cohort effect 1.68; 200 qualifying. |
| determinism | SKIP. No duplicate seeds in the profile. |

Polities alive at the end: 4 worlds with 1, 51 with 2, 108 with 3 and 37
with 4. "exceeds 2x capacity" warnings: 33 in the whole run.

The first full run, before correction 10, failed only regression
`latest_satisfaction_mean` (0.6502 against the 0.65 ceiling; everything else
passed, with all-initial-civ survival 0.15, 0 of 200 extinct, final
population min 42 / median 188). That run is the evidence for correction 10.

### Subset (20 seeds × 200 turns, hybrid)

**PASS**, `validation_compare` **NO REGRESSION**.

| Oracle | `db26681` | Branch head |
| --- | --- | --- |
| regression | FAIL `civ_survival` (informational in subset) | PASS, strict |
| satisfaction mean / latest | 0.481 / 0.454 | 0.585 / 0.595 |
| migration / rebellion per agent-turn | 0.0505 / 0.0513 | 0.0589 / 0.0437 |
| all-initial-civ survival | 0.25 | 0.15 |
| Gini in range | 97% | 85% |
| occupation violations | 0.11% | 0.28% |
| final population min / median / max | 207 / 398 / 551 | 106 / 197 / 295 |
| artifacts | PARTIAL (loss 0.5%) | PARTIAL (loss 1.3%; the loss band is calibrated for 500 turns) |
| arcs / era / needs / cohort / community | PASS | PASS |
| determinism | SKIP | SKIP |

## Open items

These limit the food economy further and are documented, not changed:

- **Winter.** Grain is seasonal (spring 0.8, summer 1.2, autumn 1.5, winter
  0.3). Plains enter winter with about 1.3 turns of demand in store and run
  short in about two thirds of winter region-turns (median sufficiency
  0.33). In seed 43, fed regions export about 11% of their demand per turn
  as merchant cargo, while 73% of food deliveries land in regions that are
  already fed: M58 routes by a generic market margin, not by the
  destination's need for the good carried (a caveat M58a documents).
  Goods-aware routing or a seasonal storage motive would help; both are trade
  design changes.
- **Locust swarms.** M35b fires a swarm with probability 0.15 per eligible
  summer or autumn turn for 2-3 turns, and its cooldown equals its duration.
  Eligible grain regions lose their crop in 18-33% of summer and autumn
  region-turns, roughly a fifth of the annual grain harvest. This is the
  spec's rate; whether it is intended is a design question.
- **Drought and cooling.** The crop climate modifier (drought 0.5, cooling
  0.7) and the water loss of the same phases compound: plains soil × water
  falls to about 0.10 in cooling phases, so crops yield 5-30% of normal for 30
  of every 75 turns. Both are M23/M34 design.
- **Occupational dead band.** Agents switch only into an occupation with
  supply below two thirds of demand. For farmers (target about 0.6) that is a
  20-point gap, for merchants a 3-point one, so excess accumulates in the
  small occupations: seed 43 still runs at 51% farmers against 59% and 18%
  merchants against 11%. Changing the switching rule is an agent-behavior
  calibration outside this pass.
- **Regions without a food resource.** Mountains, forests and most tundra and
  desert slots produce no food in the goods economy and depend on imports;
  they are now often unpopulated rather than overfilled. The aggregate model's
  M34 subsistence baseline (0.15 × crop climate) has no goods-economy
  counterpart.
- **Smaller populations.** Regions now settle at about two thirds of
  capacity. Full-profile final populations are 33 / 182 / 325 (min / median /
  max) against 212 / 452 / 598 in the extinction fix's gate, and the five
  smallest worlds hold 33-52 agents at turn 500. None died, but if small
  worlds matter downstream, the capacity tables or the brake band are the
  levers.
- **Satisfaction margin.** Latest satisfaction in the full gate is 0.643
  against the unchanged 0.65 ceiling; further food improvements will reach it
  again unless the remaining floor-era tunings are revisited.
- **Satisfaction model.** Other M47c-M57 satisfaction tunings (the stability
  bonus, class-tension and persecution weights) were also made to meet the
  regression floor on dying worlds. Only the food weight is recalibrated
  here; the rest belongs to the satisfaction owners.
- **`civ_survival` band.** It passes on the branch head (0.15 in the
  subset, 0.165 in the full profile), but the base subset and an intermediate branch state sat at 0.25
  against the 0.20 limit. The fisheries promotion note already recommends
  recalibrating this band for living worlds; it is unchanged here.
- **Fishing effort** still does not respond to falling catch per fisher; the
  optional adaptive-effort item was not attempted.
- **Secession threshold.** The extinction fix left it at 10 pending "the
  ecology-goods balance sweep"; it can be revisited on these worlds.
- **Overlap with epidemiology work.** Correction 9 changes plague contagion in
  `events.py`; the epidemiology branch should rebase onto it or review it.

## Reproduction

The probe and analysis scripts used for the measurements live outside the
repository. The measurements come from ordinary runs
(`python -m chronicler.main --seed S --turns T --agents hybrid --simulate-only`,
with `--worldgen procedural --regions 64 --civs 16` for the procedural
worlds), reading `EconomyResult.food_sufficiency`, stockpiles and region
populations each turn. The gates are `scripts/m53b_run_validation.py
--profile subset|full --parallel 2`, with the `db26681` subset report as the
comparison baseline.
